# experiments/urls.py
from django.urls import path
from . import sweep_views, views

urlpatterns = [
    path('', views.list_experiments, name='list_experiments'),
    path('create/', views.create_experiment, name='create_experiment'),
    path('sweeps/', sweep_views.sweeps, name='sweeps'),
    path('sweeps/preview/', sweep_views.preview_sweep, name='preview_sweep'),
    path('sweeps/<uuid:batch_id>/', sweep_views.sweep_detail, name='sweep_detail'),
    path('sweeps/<uuid:batch_id>/cancel/', sweep_views.cancel_sweep, name='cancel_sweep'),
    path('scripts/<uuid:script_id>/run/', views.run_script, name='run_script'),
    path('<uuid:experiment_id>/result/', views.download_experiment_result, name='download_experiment_result'),
    path('<uuid:experiment_id>/delete/', views.delete_experiment, name='delete_experiment'),
    path('<uuid:experiment_id>/', views.get_experiment_detail, name='get_experiment'),
    path('<uuid:experiment_id>/run/', views.run_experiment, name='run_experiment'),
]
