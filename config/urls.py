from django.urls import path

from routing.views import route_plan

urlpatterns = [path("api/route/", route_plan, name="route-plan")]
