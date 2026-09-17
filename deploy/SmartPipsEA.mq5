//+------------------------------------------------------------------+
//|                                                  SmartPipsEA.mq5  |
//|   Bridges your MT5 terminal to the SmartPips server:              |
//|     - auto-detects the broker's gold & silver symbols            |
//|     - pushes account + quotes + candles every few seconds        |
//|     - polls the server for queued orders and executes them       |
//|                                                                  |
//|   SETUP (one time):                                              |
//|   1) In MT5: Tools > Options > Expert Advisors >                 |
//|      "Allow WebRequest for listed URL" and add:                  |
//|         https://smartpips.ir                                     |
//|   2) Attach this EA to ANY chart (it finds gold/silver itself).  |
//|   3) Set BridgeKey below to the same value as MT5_BRIDGE_KEY     |
//|      in the server's .env                                        |
//+------------------------------------------------------------------+
#property copyright "SmartPips"
#property version   "1.0"
#property strict

input string ServerUrl  = "https://smartpips.ir"; // server base URL
input string BridgeKey  = "CHANGE_ME";            // == MT5_BRIDGE_KEY in server .env
input double DefaultLot = 0.01;                    // fallback lot if server sends 0
input int    PushSeconds = 5;                       // how often to push data
input bool   EnableTrading = true;                  // execute queued orders

string GoldSymbol = "";
string SilverSymbol = "";
datetime lastPush = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   DetectSymbols();
   EventSetTimer(1);
   Print("SmartPipsEA started. Gold=", GoldSymbol, " Silver=", SilverSymbol);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason) { EventKillTimer(); }

//+------------------------------------------------------------------+
//| Find the broker's gold/silver symbol names automatically         |
//+------------------------------------------------------------------+
void DetectSymbols()
  {
   int total = SymbolsTotal(false);
   for(int i=0; i<total; i++)
     {
      string name = SymbolName(i, false);
      string up = name;
      StringToUpper(up);
      if(GoldSymbol=="" && (StringFind(up,"XAU")>=0 || StringFind(up,"GOLD")>=0))
         GoldSymbol = name;
      if(SilverSymbol=="" && (StringFind(up,"XAG")>=0 || StringFind(up,"SILVER")>=0))
         SilverSymbol = name;
     }
   if(GoldSymbol!="")   SymbolSelect(GoldSymbol, true);
   if(SilverSymbol!="") SymbolSelect(SilverSymbol, true);
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   if(TimeCurrent() - lastPush >= PushSeconds)
     {
      PushData();
      if(EnableTrading) PollOrders();
      lastPush = TimeCurrent();
     }
  }

//+------------------------------------------------------------------+
//| Build a JSON candle array for a symbol/timeframe                 |
//+------------------------------------------------------------------+
string CandlesJson(string symbol, ENUM_TIMEFRAMES tf, int count)
  {
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int got = CopyRates(symbol, tf, 0, count, rates);
   if(got <= 0) return "[]";
   string s = "[";
   // oldest -> newest
   for(int i=got-1; i>=0; i--)
     {
      s += StringFormat("{\"time\":%I64d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%I64d}",
                        (long)rates[i].time, rates[i].open, rates[i].high,
                        rates[i].low, rates[i].close, (long)rates[i].tick_volume);
      if(i>0) s += ",";
     }
   s += "]";
   return s;
  }

string TfLabel(ENUM_TIMEFRAMES tf)
  {
   switch(tf)
     {
      case PERIOD_M1:  return "1m";
      case PERIOD_M5:  return "5m";
      case PERIOD_M15: return "15m";
      case PERIOD_H1:  return "1h";
      case PERIOD_H4:  return "4h";
      default:         return "5m";
     }
  }

string QuoteJson(string canonical, string broker)
  {
   if(broker=="") return "";
   MqlTick t;
   if(!SymbolInfoTick(broker, t)) return "";
   return StringFormat("{\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f}", canonical, t.bid, t.ask);
  }

string CandleBlock(string canonical, string broker, ENUM_TIMEFRAMES tf)
  {
   if(broker=="") return "";
   return StringFormat("{\"symbol\":\"%s\",\"timeframe\":\"%s\",\"candles\":%s}",
                       canonical, TfLabel(tf), CandlesJson(broker, tf, 300));
  }

//+------------------------------------------------------------------+
//| Push account + quotes + candles to the server                    |
//+------------------------------------------------------------------+
void PushData()
  {
   string acc = StringFormat(
      "{\"login\":\"%I64d\",\"broker\":\"%s\",\"currency\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,"
      "\"margin\":%.2f,\"free_margin\":%.2f,\"leverage\":%d,\"profit\":%.2f,"
      "\"gold_symbol\":\"%s\",\"silver_symbol\":\"%s\"}",
      (long)AccountInfoInteger(ACCOUNT_LOGIN),
      AccountInfoString(ACCOUNT_COMPANY),
      AccountInfoString(ACCOUNT_CURRENCY),
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoDouble(ACCOUNT_MARGIN),
      AccountInfoDouble(ACCOUNT_MARGIN_FREE),
      (int)AccountInfoInteger(ACCOUNT_LEVERAGE),
      AccountInfoDouble(ACCOUNT_PROFIT),
      GoldSymbol, SilverSymbol);

   // quotes
   string quotes = "";
   string gq = QuoteJson("XAUUSD", GoldSymbol);
   string sq = QuoteJson("XAGUSD", SilverSymbol);
   if(gq!="") quotes += gq;
   if(sq!="") { if(quotes!="") quotes += ","; quotes += sq; }

   // candles: gold 5m+15m, silver 5m
   string candles = "";
   string blocks[5];
   int n=0;
   string b;
   b = CandleBlock("XAUUSD", GoldSymbol, PERIOD_M5);  if(b!="") blocks[n++]=b;
   b = CandleBlock("XAUUSD", GoldSymbol, PERIOD_M15); if(b!="") blocks[n++]=b;
   b = CandleBlock("XAGUSD", SilverSymbol, PERIOD_M5);if(b!="") blocks[n++]=b;
   for(int i=0;i<n;i++){ candles += blocks[i]; if(i<n-1) candles += ","; }

   string body = StringFormat("{\"account\":%s,\"quotes\":[%s],\"candles\":[%s]}",
                              acc, quotes, candles);

   SendPost("/api/mt5/push/", body);
  }

//+------------------------------------------------------------------+
//| Poll queued orders and execute them                              |
//+------------------------------------------------------------------+
void PollOrders()
  {
   string resp = SendGet("/api/mt5/orders/pending/");
   if(resp=="" || resp=="[]") return;

   // Very small JSON array parser for our known shape.
   int pos = 0;
   while(true)
     {
      int objStart = StringFind(resp, "{", pos);
      if(objStart < 0) break;
      int objEnd = StringFind(resp, "}", objStart);
      if(objEnd < 0) break;
      string obj = StringSubstr(resp, objStart, objEnd-objStart+1);
      pos = objEnd+1;

      long   id     = (long)JsonNum(obj, "id");
      string bsym   = JsonStr(obj, "broker_symbol");
      string action = JsonStr(obj, "action");
      double vol    = JsonNum(obj, "volume");
      double sl     = JsonNum(obj, "sl");
      double tp     = JsonNum(obj, "tp");
      if(vol<=0) vol = DefaultLot;
      if(bsym=="") continue;

      ExecuteOrder(id, bsym, action, vol, sl, tp);
     }
  }

void ExecuteOrder(long id, string symbol, string action, double vol, double sl, double tp)
  {
   SymbolSelect(symbol, true);
   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action   = TRADE_ACTION_DEAL;
   req.symbol   = symbol;
   req.volume   = vol;
   req.type     = (action=="buy") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price    = (action=="buy") ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                                   : SymbolInfoDouble(symbol, SYMBOL_BID);
   req.sl       = sl;
   req.tp       = tp;
   req.deviation= 20;
   req.type_filling = ORDER_FILLING_IOC;

   bool ok = OrderSend(req, res);
   string status = (ok && res.retcode==TRADE_RETCODE_DONE) ? "filled" : "rejected";
   string msg = StringFormat("retcode=%d", res.retcode);
   string body = StringFormat("{\"status\":\"%s\",\"ticket\":%I64d,\"message\":\"%s\"}",
                              status, (long)res.order, msg);
   SendPost(StringFormat("/api/mt5/orders/%I64d/ack/", id), body);
  }

//+------------------------------------------------------------------+
//| Tiny JSON helpers (for the flat objects we control)              |
//+------------------------------------------------------------------+
double JsonNum(string obj, string key)
  {
   string k = "\""+key+"\":";
   int p = StringFind(obj, k);
   if(p<0) return 0;
   p += StringLen(k);
   string rest = StringSubstr(obj, p);
   return StringToDouble(rest);
  }

string JsonStr(string obj, string key)
  {
   string k = "\""+key+"\":\"";
   int p = StringFind(obj, k);
   if(p<0) return "";
   p += StringLen(k);
   int e = StringFind(obj, "\"", p);
   if(e<0) return "";
   return StringSubstr(obj, p, e-p);
  }

//+------------------------------------------------------------------+
//| HTTP helpers using WebRequest                                    |
//+------------------------------------------------------------------+
string SendPost(string path, string body)
  {
   string url = ServerUrl + path;
   string headers = "Content-Type: application/json\r\nX-Bridge-Key: " + BridgeKey + "\r\n";
   char post[], result[];
   StringToCharArray(body, post, 0, StringLen(body));
   // drop the trailing null added by StringToCharArray
   ArrayResize(post, ArraySize(post)-1);
   string rh;
   int timeout = 5000;
   int code = WebRequest("POST", url, headers, timeout, post, result, rh);
   if(code == -1)
      Print("WebRequest error ", GetLastError(), " (did you allow ", ServerUrl, " in Options?)");
   return CharArrayToString(result);
  }

string SendGet(string path)
  {
   string url = ServerUrl + path;
   string headers = "X-Bridge-Key: " + BridgeKey + "\r\n";
   char post[], result[];
   string rh;
   int code = WebRequest("GET", url, headers, 5000, post, result, rh);
   if(code == -1)
      Print("WebRequest GET error ", GetLastError());
   return CharArrayToString(result);
  }
//+------------------------------------------------------------------+
