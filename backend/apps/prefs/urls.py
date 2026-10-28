from django.urls import path

from .views import (my_access, all_access, user_access,
                    my_limits, all_limits, user_limits)

urlpatterns = [
    path("market_access/", my_access),
    path("market_access/all/", all_access),
    path("market_access/<int:user_id>/", user_access),
    path("risk_limits/", my_limits),
    path("risk_limits/all/", all_limits),
    path("risk_limits/<int:user_id>/", user_limits),
]
