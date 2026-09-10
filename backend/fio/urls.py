from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse

from api.router import api


@ensure_csrf_cookie
def csrf(_request):
    """Planta o cookie csrftoken para o front mandar no header X-CSRFToken."""
    return JsonResponse({"ok": True})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/csrf", csrf),
    path("api/", api.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
