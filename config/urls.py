from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from work.views.index import index

urlpatterns = [
    path('admin/', admin.site.urls),
    path('telegram/', include('telegram.urls', namespace='telegram')),
    path('work/', include('work.urls', namespace='work')),
    path('vacancy/', include('vacancy.urls', namespace='vacancy')),
    path('', index, name='index'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)