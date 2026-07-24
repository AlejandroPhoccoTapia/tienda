from django.urls import path

from . import views

app_name = "negocio"

urlpatterns = [
    path("", views.productos, name="productos"),
    path("productos/nuevo/", views.producto_crear, name="producto_crear"),
    path(
        "productos/<int:producto_id>/eliminar/",
        views.producto_eliminar,
        name="producto_eliminar",
    ),
    path("pedidos/", views.pedidos, name="pedidos"),
    path("pedidos/nuevo/", views.pedido_crear, name="pedido_crear"),
    path(
        "pedidos/<int:pedido_id>/eliminar/",
        views.pedido_eliminar,
        name="pedido_eliminar",
    ),
    path("pedidos/<int:pedido_id>/", views.pedido_detalle, name="pedido_detalle"),
    path("ventas/", views.ventas, name="ventas"),
    path("ventas/nueva/", views.venta_crear, name="venta_crear"),
    path("catalogos/", views.catalogos, name="catalogos"),
    path(
        "catalogos/marcas/<int:marca_id>/eliminar/",
        views.marca_eliminar,
        name="marca_eliminar",
    ),
    path(
        "catalogos/tipos/<int:tipo_id>/eliminar/",
        views.tipo_eliminar,
        name="tipo_eliminar",
    ),
]
