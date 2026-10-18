from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

# Institutional Branding & Security Headers for Django Admin
admin.site.site_header = "Sofiz Treasury & Liquidity Operations"
admin.site.site_title = "Sofiz Vault Administration"
admin.site.index_title = "Institutional Security & Control Portal"

def root_health_view(request):
    return JsonResponse({
        "status": "online",
        "service": "Sofiz Treasury & Liquidity Core",
        "version": "2.4.0"
    })

urlpatterns = [
    # Obfuscated Secret Admin Route
    path(settings.ADMIN_URL_PATH, admin.site.urls),
    path('api/', include('monitoring.api_urls')),
    path('api/projects/', include('projects.urls')),
    path('', include('monitoring.urls')),
    path('', root_health_view, name='root_health'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

