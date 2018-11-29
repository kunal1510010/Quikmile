# from django.conf.urls import url
from . import views
from django.conf.urls import url

app_name = 'Site'

urlpatterns = [
        url(r'^home/$', views.home, name='home')
]