from django.urls import path, include
from .views import reset_db

urlpatterns = [
    path('reset-db-DANGER/', reset_db, name='reset_db'), #reset the test DB for running e2e tests
]