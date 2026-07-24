from django.contrib import admin

from .models import (
    Cliente,
    DetalleVenta,
    DistribucionGanancia,
    InventarioLote,
    Marca,
    Paquete,
    Pedido,
    PersonaGanancia,
    Producto,
    SalidaInventario,
    TipoPago,
    TipoProducto,
    Venta,
)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "marca", "tipo_producto")
    list_filter = ("marca", "tipo_producto")
    search_fields = ("nombre",)


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("id", "fecha", "cuenta", "propietario")
    date_hierarchy = "fecha"


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ("id", "fecha", "cliente", "tipo_pago", "pagado", "estado_entrega")
    list_filter = ("tipo_pago", "pagado", "estado_entrega")
    date_hierarchy = "fecha"


admin.site.register(
    [
        Marca,
        TipoProducto,
        Paquete,
        InventarioLote,
        Cliente,
        TipoPago,
        DetalleVenta,
        SalidaInventario,
        PersonaGanancia,
        DistribucionGanancia,
    ]
)
