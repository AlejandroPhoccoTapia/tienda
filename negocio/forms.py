from django import forms
from django.db.models import F, IntegerField, Sum, Value
from django.db.models.functions import Coalesce

from .models import (
    Cliente,
    DetalleVenta,
    InventarioLote,
    Marca,
    Paquete,
    Pedido,
    Producto,
    TipoProducto,
    TipoPago,
    Venta,
)


def lotes_con_stock():
    return (
        InventarioLote.objects.select_related(
            "producto", "paquete", "paquete__pedido"
        )
        .annotate(
            cantidad_usada=Coalesce(
                Sum("salidas__cantidad"), Value(0), output_field=IntegerField()
            )
        )
        .annotate(stock_disponible=F("cantidad_inicial") - F("cantidad_usada"))
        .filter(paquete__entregado=True, stock_disponible__gt=0)
        .order_by("producto__nombre", "paquete__pedido__fecha", "id")
    )


class LoteSelect(forms.Select):
    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        instancia = getattr(value, "instance", None)
        if instancia is not None:
            option["attrs"]["data-stock"] = instancia.stock_disponible
            option["attrs"]["data-cost"] = f"{instancia.costo_unitario_soles:.2f}"
        return option


class LoteChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, lote):
        codigo = lote.paquete.codigo_seguimiento or f"Paquete #{lote.paquete_id}"
        return (
            f"{lote.producto.nombre} · Lote #{lote.id} ({codigo}) · "
            f"Costo S/ {lote.costo_unitario_soles:.2f} · "
            f"Disponible: {lote.stock_disponible}"
        )


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"


class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = [
            "cuenta",
            "propietario",
            "direccion",
            "fecha",
            "descuento",
            "dolar_valor",
        ]
        labels = {
            "cuenta": "Cuenta de compra",
            "propietario": "Propietario",
            "direccion": "Dirección o casillero",
            "fecha": "Fecha del pedido",
            "descuento": "Descuento (S/)",
            "dolar_valor": "Valor del dólar",
        }
        widgets = {
            "cuenta": forms.TextInput(attrs={"placeholder": "Ej. Cuenta Amazon"}),
            "propietario": forms.TextInput(attrs={"placeholder": "Nombre del propietario"}),
            "direccion": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Dirección de envío o casillero"}
            ),
            "fecha": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
            "descuento": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "dolar_valor": forms.NumberInput(attrs={"min": "0", "step": "0.0001"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].input_formats = ["%Y-%m-%dT%H:%M"]


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["nombre", "marca", "tipo_producto", "link", "foto"]
        labels = {
            "nombre": "Nombre del producto",
            "marca": "Marca",
            "tipo_producto": "Tipo de producto",
            "link": "Enlace del producto",
            "foto": "Foto del producto",
        }
        widgets = {
            "nombre": forms.TextInput(
                attrs={"placeholder": "Ej. Niacinamide 10% + Zinc 1%"}
            ),
            "link": forms.URLInput(
                attrs={"placeholder": "https://tienda.com/producto"}
            ),
            "foto": forms.FileInput(
                attrs={"accept": "image/jpeg,image/png,image/webp,image/gif"}
            ),
        }


class PaquetePedidoForm(forms.ModelForm):
    class Meta:
        model = Paquete
        fields = ["codigo_seguimiento", "entregado", "fecha_entrega"]
        labels = {
            "codigo_seguimiento": "Código de seguimiento",
            "entregado": "Paquete entregado",
            "fecha_entrega": "Fecha de entrega",
        }
        widgets = {
            "codigo_seguimiento": forms.TextInput(
                attrs={"placeholder": "Opcional, ej. USPS-9400"}
            ),
            "fecha_entrega": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha_entrega"].input_formats = ["%Y-%m-%dT%H:%M"]


class LotePedidoForm(forms.ModelForm):
    class Meta:
        model = InventarioLote
        fields = [
            "producto",
            "cantidad_inicial",
            "costo_unitario_dolar",
            "costo_unitario_soles",
            "costo_soles_manual",
        ]
        labels = {
            "producto": "Producto",
            "cantidad_inicial": "Cantidad",
            "costo_unitario_dolar": "Costo unitario US$",
            "costo_unitario_soles": "Costo unitario S/",
            "costo_soles_manual": "Costo en soles ingresado manualmente",
        }
        widgets = {
            "cantidad_inicial": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "costo_unitario_dolar": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "placeholder": "0.00"}
            ),
            "costo_unitario_soles": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "placeholder": "0.00"}
            ),
        }


class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = [
            "fecha",
            "cliente",
            "tipo_pago",
            "direccion_entrega",
            "descuento",
            "pagado",
            "estado_entrega",
        ]
        labels = {
            "fecha": "Fecha de venta",
            "cliente": "Cliente",
            "tipo_pago": "Método de pago",
            "direccion_entrega": "Dirección de entrega",
            "descuento": "Descuento (S/)",
            "pagado": "Venta pagada",
            "estado_entrega": "Estado de entrega",
        }
        widgets = {
            "fecha": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
            "direccion_entrega": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Opcional"}
            ),
            "descuento": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "estado_entrega": forms.Select(
                choices=[
                    ("No entregado", "No entregado"),
                    ("Entregado", "Entregado"),
                ]
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["cliente"].required = False
        self.order_fields(
            [
                "fecha",
                "cliente",
                "tipo_pago",
                "direccion_entrega",
                "descuento",
                "pagado",
                "estado_entrega",
            ]
        )


class DetalleVentaForm(forms.ModelForm):
    inventario_lote = LoteChoiceField(
        queryset=InventarioLote.objects.none(),
        label="Producto y lote",
        empty_label="Selecciona un lote con stock",
        widget=LoteSelect,
    )
    comision_karen = forms.DecimalField(
        label="Comisión de Karen S/",
        min_value=0,
        max_digits=12,
        decimal_places=2,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )

    class Meta:
        model = DetalleVenta
        fields = ["cantidad", "precio_unitario_venta"]
        labels = {
            "cantidad": "Cantidad",
            "precio_unitario_venta": "Precio unitario de venta S/",
        }
        widgets = {
            "cantidad": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "precio_unitario_venta": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "placeholder": "0.00"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["inventario_lote"].queryset = lotes_con_stock()
        self.order_fields(
            [
                "inventario_lote",
                "cantidad",
                "precio_unitario_venta",
                "comision_karen",
            ]
        )

    def clean(self):
        cleaned_data = super().clean()
        lote = cleaned_data.get("inventario_lote")
        cantidad = cleaned_data.get("cantidad")
        if lote and cantidad and cantidad > lote.stock_disponible:
            self.add_error(
                "cantidad",
                f"Solo hay {lote.stock_disponible} unidades disponibles en este lote.",
            )
        return cleaned_data


class MarcaForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ["nombre"]
        labels = {"nombre": "Nombre de la marca"}
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Rare Beauty"})
        }


class TipoProductoForm(forms.ModelForm):
    class Meta:
        model = TipoProducto
        fields = ["nombre"]
        labels = {"nombre": "Nombre del tipo"}
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Perfumería"})
        }


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "telefono"]
        labels = {"nombre": "Nombre del cliente", "telefono": "Teléfono"}
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Ana Castillo"}),
            "telefono": forms.TextInput(attrs={"placeholder": "Ej. 999 123 456"}),
        }


class TipoPagoForm(forms.ModelForm):
    class Meta:
        model = TipoPago
        fields = ["nombre"]
        labels = {"nombre": "Nombre del método"}
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej. Plin"})
        }
