from django.db import models


class Marca(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class TipoProducto(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "tipo de producto"
        verbose_name_plural = "tipos de producto"

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    nombre = models.CharField(max_length=150)
    marca = models.ForeignKey(
        Marca, on_delete=models.SET_NULL, null=True, blank=True, related_name="productos"
    )
    tipo_producto = models.ForeignKey(
        TipoProducto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="productos",
    )
    link = models.URLField(max_length=500, blank=True)
    foto = models.ImageField(upload_to="productos/", blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Pedido(models.Model):
    cuenta = models.CharField(max_length=150, blank=True)
    propietario = models.CharField(max_length=150, blank=True)
    direccion = models.CharField(max_length=300, blank=True)
    fecha = models.DateTimeField()
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    dolar_valor = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Pedido #{self.pk}"


class Paquete(models.Model):
    pedido = models.ForeignKey(
        Pedido, on_delete=models.CASCADE, related_name="paquetes"
    )
    codigo_seguimiento = models.CharField(
        max_length=150, unique=True, null=True, blank=True
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.codigo_seguimiento or f"Paquete #{self.pk}"


class InventarioLote(models.Model):
    pedido = models.ForeignKey(
        Pedido, on_delete=models.CASCADE, related_name="lotes"
    )
    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name="lotes"
    )
    cantidad_inicial = models.PositiveIntegerField()
    cantidad_recibida = models.PositiveIntegerField(default=0)
    costo_unitario_dolar = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    costo_unitario_soles = models.DecimalField(max_digits=12, decimal_places=2)
    costo_soles_manual = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad_recibida__lte=models.F("cantidad_inicial")),
                name="inventario_recibido_no_supera_pedido",
            )
        ]
        verbose_name = "lote de inventario"
        verbose_name_plural = "lotes de inventario"

    def __str__(self):
        return f"{self.producto} · {self.cantidad_inicial} unidades"


class Cliente(models.Model):
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class TipoPago(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "tipo de pago"
        verbose_name_plural = "tipos de pago"

    def __str__(self):
        return self.nombre


class Venta(models.Model):
    fecha = models.DateTimeField()
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventas",
    )
    tipo_pago = models.ForeignKey(
        TipoPago, on_delete=models.PROTECT, related_name="ventas"
    )
    direccion_entrega = models.CharField(max_length=300, blank=True)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pagado = models.BooleanField(default=False)
    estado_entrega = models.CharField(max_length=50)
    cerrada = models.BooleanField(default=False)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Venta #{self.pk}"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(
        Venta, on_delete=models.CASCADE, related_name="detalles"
    )
    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name="detalles_venta"
    )
    cantidad = models.PositiveIntegerField()
    precio_unitario_venta = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"

    def __str__(self):
        return f"{self.venta} · {self.producto}"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario_venta


class SalidaInventario(models.Model):
    detalle_venta = models.ForeignKey(
        DetalleVenta, on_delete=models.CASCADE, related_name="salidas"
    )
    inventario_lote = models.ForeignKey(
        InventarioLote, on_delete=models.PROTECT, related_name="salidas"
    )
    cantidad = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["detalle_venta", "inventario_lote"],
                name="salida_detalle_lote_unica",
            )
        ]
        verbose_name = "salida de inventario"
        verbose_name_plural = "salidas de inventario"

    def __str__(self):
        return f"{self.detalle_venta} · {self.cantidad}"


class PersonaGanancia(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "persona de ganancia"
        verbose_name_plural = "personas de ganancia"

    def __str__(self):
        return self.nombre


class DistribucionGanancia(models.Model):
    venta = models.ForeignKey(
        Venta, on_delete=models.CASCADE, related_name="distribuciones"
    )
    detalle_venta = models.ForeignKey(
        DetalleVenta,
        on_delete=models.CASCADE,
        related_name="distribuciones_ganancia",
        null=True,
        blank=True,
    )
    persona = models.ForeignKey(
        PersonaGanancia, on_delete=models.PROTECT, related_name="distribuciones"
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    pagado = models.BooleanField(default=False)
    fecha_pago = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["detalle_venta", "persona"],
                name="distribucion_detalle_persona_unica",
            )
        ]
        ordering = ["persona__nombre"]
        verbose_name = "distribución de ganancia"
        verbose_name_plural = "distribuciones de ganancia"

    def __str__(self):
        return f"{self.venta} · {self.persona}"
