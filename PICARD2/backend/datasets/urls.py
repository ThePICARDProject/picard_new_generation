from django.urls import path
from . import views


urlpatterns = [
    path('upload/csv/', views.upload_csv, name='upload_csv'),
    path('<uuid:dataset_id>/', views.delete_dataset, name='delete_dataset'),
    path('', views.list_datasets, name='list_datasets')
]