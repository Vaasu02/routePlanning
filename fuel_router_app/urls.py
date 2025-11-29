from django.urls import path
from fuel_router_app.views import RoutePlannerView

urlpatterns = [
    path('plan-route/', RoutePlannerView.as_view(), name='plan-route'),
]