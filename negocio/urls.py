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
    path(
        "ventas/<int:venta_id>/editar/",
        views.venta_editar,
        name="venta_editar",
    ),
    path(
        "ventas/<int:venta_id>/productos/agregar/",
        views.venta_producto_agregar,
        name="venta_producto_agregar",
    ),
    path(
        "ventas/productos/<int:detalle_id>/editar/",
        views.detalle_venta_editar,
        name="detalle_venta_editar",
    ),
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
    path(
        "catalogos/clientes/<int:cliente_id>/editar/",
        views.cliente_editar,
        name="cliente_editar",
    ),
    path(
        "catalogos/clientes/<int:cliente_id>/eliminar/",
        views.cliente_eliminar,
        name="cliente_eliminar",
    ),
    path(
        "catalogos/pagos/<int:pago_id>/editar/",
        views.pago_editar,
        name="pago_editar",
    ),
    path(
        "catalogos/pagos/<int:pago_id>/eliminar/",
        views.pago_eliminar,
        name="pago_eliminar",
    ),
]
