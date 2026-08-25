from django.urls import path
from . import views


urlpatterns = [
    path('upload/', views.upload_script, name='upload_script'),
    path('<uuid:script_id>/', views.delete_script, name='delete_script'),
    path('', views.list_scripts, name='list_scripts'),
]