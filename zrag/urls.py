from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from zrag.api.urls import urlpatterns as api_urlpatterns

urlpatterns = api_urlpatterns + [
    path('v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('v1/docs/', SpectacularSwaggerView.as_view(url='/zrag/v1/schema/'), name='swagger-ui'),
]
