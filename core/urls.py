from django.urls import path
from . import views

urlpatterns = [
    # Public Form URLs
    path('form/success/', views.form_success_view, name='form_success'),
    path('form/<slug:slug>/', views.student_form_view, name='student_form'),
    

    # Admin Panel URLs
    path('', views.dashboard_view, name='dashboard'),
    path('admin-panel/login/', views.admin_login_view, name='admin_login'),
    path('admin-panel/logout/', views.admin_logout_view, name='admin_logout'),
    path('admin-panel/dashboard/', views.dashboard_view, name='dashboard'),
    
    # Form Management
    path('admin-panel/form/create/', views.create_or_edit_form_view, name='create_form'),
    path('admin-panel/form/edit/<int:form_id>/', views.create_or_edit_form_view, name='edit_form'),
    path('admin-panel/form/duplicate/<int:form_id>/', views.duplicate_form_view, name='duplicate_form'),
    path('admin-panel/form/delete/<int:form_id>/', views.delete_form_view, name='delete_form'),

    # Submission Management
    path('admin-panel/form/<int:form_id>/submissions/', views.view_submissions_view, name='view_submissions'),
    path('admin-panel/submission/delete/<int:submission_id>/', views.delete_submission_view, name='delete_submission'),
    
    # Data Export
    path('admin-panel/form/<int:form_id>/export/excel/', views.export_excel_view, name='export_excel'),
    path('admin-panel/form/<int:form_id>/export/zip/', views.export_photos_zip_view, name='export_zip'),
]