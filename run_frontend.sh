#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/frontend"
npm install
echo ">> Frontend dev server at http://localhost:5173"
npm run dev
