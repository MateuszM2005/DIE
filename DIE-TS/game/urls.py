from django.urls import path
from . import views

app_name = "game"

urlpatterns = [
    path('', views.play_game, name='play'),

    path('api/auth/status/', views.auth_status, name='auth_status'),
    path('api/auth/login/', views.login_api, name='login_api'),
    path('api/auth/logout/', views.logout_api, name='logout_api'),
    path('api/auth/register/', views.register_api, name='register_api'),
    path('api/auth/change-password/', views.change_password_api, name='change_password_api'),
    path('api/score/submit/', views.submit_score_api, name='submit_score_api'),
    path('api/leaderboard/stream/', views.leaderboard_stream_api, name='leaderboard_stream_api'),
]