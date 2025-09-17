# pescara_site/urls.py
from django.contrib import admin
from django.urls import path, include

# IMPORTS NECESARIOS PARA MEDIA EN DEV:
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("stats.urls")),   # ok aunque esté vacío por ahora
]

# Solo en DEBUG servimos media:
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)