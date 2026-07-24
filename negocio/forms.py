from django import forms
from django.db.models import Case, F, IntegerField, Sum, Value, When
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


def lotes_con_stock(incluir_lote_id=None, cantidad_reintegrada=0):
    reintegro = Case(
        When(pk=incluir_lote_id, then=Value(cantidad_reintegrada)),
        default=Value(0),
        output_field=IntegerField(),
    )
    return (
        InventarioLote.objects.select_related(
            "producto", "pedido"
        )
        .annotate(
            cantidad_usada=Coalesce(
                Sum("salidas__cantidad"), Value(0), output_field=IntegerField()
            )
        )
        .annotate(
            stock_disponible=F("cantidad_recibida") - F("cantidad_usada") + reintegro
        )
        .filter(stock_disponible__gt=0)
        .order_by("producto__nombre", "pedido__fecha", "id")
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
        return (
            f"{lote.producto.nombre} · "
            f"S/{lote.costo_unitario_soles:.2f} · "
            f"Stock {lote.stock_disponible}"
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
        fields = ["codigo_seguimiento"]
        labels = {
            "codigo_seguimiento": "Código de seguimiento",
        }
        widgets = {
            "codigo_seguimiento": forms.TextInput(
                attrs={"placeholder": "Opcional, ej. USPS-9400"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["codigo_seguimiento"].required = True


class LotePedidoForm(forms.ModelForm):
    class Meta:
        model = InventarioLote
        fields = [
            "producto",
            "cantidad_inicial",
            "cantidad_recibida",
            "costo_unitario_dolar",
            "costo_unitario_soles",
            "costo_soles_manual",
        ]
        labels = {
            "producto": "Producto",
            "cantidad_inicial": "Cantidad pedida",
            "cantidad_recibida": "Cantidad recibida",
            "costo_unitario_dolar": "Costo unitario US$",
            "costo_unitario_soles": "Costo unitario S/",
            "costo_soles_manual": "Costo en soles ingresado manualmente",
        }
        widgets = {
            "cantidad_inicial": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "cantidad_recibida": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "costo_unitario_dolar": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "placeholder": "0.00"}
            ),
            "costo_unitario_soles": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "placeholder": "0.00"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        pedida = cleaned_data.get("cantidad_inicial")
        recibida = cleaned_data.get("cantidad_recibida")
        if pedida is not None and recibida is not None and recibida > pedida:
            self.add_error(
                "cantidad_recibida",
                "La cantidad recibida no puede superar la cantidad pedida.",
            )
        return cleaned_data


class InventarioRecibidoForm(forms.ModelForm):
    class Meta:
        model = InventarioLote
        fields = ["cantidad_recibida"]
        labels = {"cantidad_recibida": "Recibidos"}
        widgets = {
            "cantidad_recibida": forms.NumberInput(attrs={"min": "0", "step": "1"})
        }

    def clean_cantidad_recibida(self):
        recibida = self.cleaned_data["cantidad_recibida"]
        if recibida > self.instance.cantidad_inicial:
            raise forms.ValidationError(
                "No puede superar la cantidad pedida."
            )
        vendida = self.instance.salidas.aggregate(
            total=Coalesce(Sum("cantidad"), Value(0), output_field=IntegerField())
        )["total"]
        if recibida < vendida:
            raise forms.ValidationError(
                f"No puede ser menor que las {vendida} unidades ya vendidas."
            )
        return recibida


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


class VentaEditarForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = [
            "cliente",
            "tipo_pago",
            "direccion_entrega",
            "descuento",
            "pagado",
            "estado_entrega",
        ]
        labels = {
            "cliente": "Cliente",
            "tipo_pago": "Método de pago",
            "direccion_entrega": "Dirección",
            "descuento": "Descuento S/",
            "pagado": "Pagado",
            "estado_entrega": "Entrega",
        }
        widgets = {
            "direccion_entrega": forms.TextInput(attrs={"placeholder": "Opcional"}),
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
        self.fields["cliente"].required = False


class DetalleVentaForm(forms.ModelForm):
    inventario_lote = LoteChoiceField(
        queryset=InventarioLote.objects.none(),
        label="Producto",
        empty_label="Selecciona un producto",
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
        lote_actual = None
        cantidad_actual = 0
        if self.instance and self.instance.pk:
            salida = self.instance.salidas.select_related("inventario_lote").first()
            if salida:
                lote_actual = salida.inventario_lote
                cantidad_actual = salida.cantidad
                self.initial["inventario_lote"] = lote_actual
            distribucion = self.instance.distribuciones_ganancia.filter(
                persona__nombre__iexact="Karen"
            ).first()
            if distribucion:
                self.initial["comision_karen"] = distribucion.monto
        self.fields["inventario_lote"].queryset = lotes_con_stock(
            lote_actual.id if lote_actual else None,
            cantidad_actual,
        )
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
                f"Solo hay {lote.stock_disponible} unidades disponibles de esta opción.",
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
