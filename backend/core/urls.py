from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, SourceViewSet, ProductViewSet,
    ParseRunViewSet, ParseErrorViewSet
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'sources', SourceViewSet, basename='source')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'parse-runs', ParseRunViewSet, basename='parserun')
router.register(r'parse-errors', ParseErrorViewSet, basename='parseerror')

urlpatterns = [
    path('', include(router.urls)),
]
