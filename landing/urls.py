__author__ = 'jblowe'

from django.urls import include, path
from landing import views

urlpatterns = [
    path('', views.index, name='index'),
    path('applist/', views.applist, name='applist'),
]
