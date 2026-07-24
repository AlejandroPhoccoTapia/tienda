from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear
from django.contrib import messages
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    ClienteForm,
    DetalleVentaForm,
    InventarioRecibidoForm,
    LotePedidoForm,
    MarcaForm,
    PaquetePedidoForm,
    PedidoForm,
    ProductoForm,
    TipoProductoForm,
    TipoPagoForm,
    VentaEditarForm,
    VentaForm,
    lotes_con_stock,
)
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


def _entero_acotado(valor, predeterminado=1, minimo=1, maximo=30):
    try:
        return max(minimo, min(int(valor), maximo))
    except (TypeError, ValueError):
        return predeterminado


def _margen_formulario_detalle(form):
    lote = form.cleaned_data["inventario_lote"]
    cantidad = Decimal(form.cleaned_data["cantidad"])
    precio = form.cleaned_data["precio_unitario_venta"]
    comision = form.cleaned_data.get("comision_karen") or Decimal("0")
    costo = cantidad * lote.costo_unitario_soles
    return cantidad * precio - costo - comision


def _validar_detalle_sin_perdida(form):
    margen = _margen_formulario_detalle(form)
    if margen >= 0:
        return margen
    lote = form.cleaned_data["inventario_lote"]
    cantidad = Decimal(form.cleaned_data["cantidad"])
    comision = form.cleaned_data.get("comision_karen") or Decimal("0")
    precio_minimo = (
        lote.costo_unitario_soles + (comision / cantidad)
    ).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    form.add_error(
        "precio_unitario_venta",
        f"Para no tener pérdidas, el precio unitario mínimo es S/{precio_minimo}.",
    )
    return None


def _margen_venta_actual(venta, omitir_detalle_id=None):
    detalles = (
        venta.detalles.exclude(pk=omitir_detalle_id)
        .prefetch_related(
            "salidas__inventario_lote",
            "distribuciones_ganancia__persona",
        )
    )
    margen_total = Decimal("0")
    hay_linea_negativa = False
    for detalle in detalles:
        venta_producto = Decimal(detalle.cantidad) * detalle.precio_unitario_venta
        costo = sum(
            (
                Decimal(salida.cantidad)
                * salida.inventario_lote.costo_unitario_soles
                for salida in detalle.salidas.all()
            ),
            Decimal("0"),
        )
        comision = sum(
            (
                distribucion.monto
                for distribucion in detalle.distribuciones_ganancia.all()
                if distribucion.persona.nombre.casefold() == "karen"
            ),
            Decimal("0"),
        )
        margen = venta_producto - costo - comision
        margen_total += margen
        hay_linea_negativa = hay_linea_negativa or margen < 0
    return margen_total, hay_linea_negativa


def _primer_error_formulario(form, predeterminado):
    return next(
        (
            str(mensaje)
            for mensajes in form.errors.values()
            for mensaje in mensajes
        ),
        predeterminado,
    )


def productos(request):
    marca_id = request.GET.get("marca", "")
    tipo_id = request.GET.get("tipo", "")

    entradas = (
        InventarioLote.objects.filter(producto_id=OuterRef("pk"))
        .values("producto_id")
        .annotate(total=Sum("cantidad_recibida"))
        .values("total")
    )
    salidas = (
        SalidaInventario.objects.filter(
            inventario_lote__producto_id=OuterRef("pk"),
        )
        .values("inventario_lote__producto_id")
        .annotate(total=Sum("cantidad"))
        .values("total")
    )
    items = Producto.objects.select_related("marca", "tipo_producto").annotate(
        entradas=Coalesce(
            Subquery(entradas), Value(0), output_field=IntegerField()
        ),
        salidas=Coalesce(Subquery(salidas), Value(0), output_field=IntegerField()),
    )
    items = items.annotate(stock=F("entradas") - F("salidas"))

    if marca_id.isdigit():
        items = items.filter(marca_id=marca_id)
    if tipo_id.isdigit():
        items = items.filter(tipo_producto_id=tipo_id)

    return render(
        request,
        "negocio/productos.html",
        {
            "productos": items,
            "marcas": Marca.objects.all(),
            "tipos": TipoProducto.objects.all(),
            "marca_seleccionada": marca_id,
            "tipo_seleccionado": tipo_id,
        },
    )


def producto_crear(request):
    if request.method == "POST":
        form = ProductoForm(request.POST, request.FILES)
        if form.is_valid():
            producto = form.save()
            messages.success(request, f"Producto “{producto.nombre}” creado.")
            return redirect("negocio:productos")
    else:
        form = ProductoForm()

    return render(
        request,
        "negocio/producto_form.html",
        {"form": form, "sin_catalogos": not Marca.objects.exists() or not TipoProducto.objects.exists()},
    )


def producto_eliminar(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    if request.method == "POST":
        nombre = producto.nombre
        try:
            producto.delete()
            messages.success(request, f"Producto “{nombre}” eliminado.")
        except ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar “{nombre}” porque ya tiene inventario o ventas.",
            )
        return redirect("negocio:productos")

    return render(
        request,
        "negocio/confirmar_eliminar.html",
        {
            "titulo": "Eliminar producto",
            "nombre": producto.nombre,
            "descripcion": "Esta acción eliminará el producto del catálogo.",
            "cancel_url": "negocio:productos",
        },
    )


def pedidos(request, contexto_creacion=None, pedido_abierto=None):
    productos_del_pedido = (
        InventarioLote.objects.select_related(
            "producto", "producto__marca", "producto__tipo_producto"
        )
        .annotate(
            cantidad_vendida=Coalesce(
                Sum("salidas__cantidad"), Value(0), output_field=IntegerField()
            )
        )
        .order_by("id")
    )
    items = (
        Pedido.objects.prefetch_related(
            "paquetes",
            Prefetch(
                "lotes",
                queryset=productos_del_pedido,
                to_attr="productos_pedido",
            ),
        )
    )
    for pedido in items:
        pedido.total_paquetes = len(pedido.paquetes.all())
        pedido.total_unidades = sum(
            (lote.cantidad_inicial for lote in pedido.productos_pedido), 0
        )
        pedido.total_recibidas = sum(
            (lote.cantidad_recibida for lote in pedido.productos_pedido), 0
        )
        pedido.costo_total = Decimal("0")
        for lote in pedido.productos_pedido:
            lote.costo_total = (
                Decimal(lote.cantidad_inicial) * lote.costo_unitario_soles
            )
            lote.stock_disponible = lote.cantidad_recibida - lote.cantidad_vendida
            lote.form_recibidos = InventarioRecibidoForm(
                instance=lote, prefix=f"recibido-{lote.id}"
            )
            pedido.costo_total += lote.costo_total

    if contexto_creacion is None:
        contexto_creacion = {
            "form": PedidoForm(initial={"fecha": timezone.localtime()}),
            "paquetes": [
                {
                    "indice": 0,
                    "form": PaquetePedidoForm(prefix="paquete-0"),
                }
            ],
            "productos_pedido_form": [
                {
                    "indice": 0,
                    "form": LotePedidoForm(prefix="producto-0"),
                }
            ],
            "total_paquetes": 1,
            "paquetes_activos": 1,
            "total_productos_pedido": 1,
            "formulario_pedido_abierto": request.GET.get("crear") == "1",
        }
    contexto_creacion["productos_disponibles"] = Producto.objects.all()

    return render(
        request,
        "negocio/pedidos.html",
        {
            "pedidos": items,
            "pedido_abierto": pedido_abierto or request.GET.get("abierto", ""),
            **contexto_creacion,
        },
    )


def pedido_crear(request):
    if request.method != "POST":
        return pedidos(
            request,
            {
                "form": PedidoForm(initial={"fecha": timezone.localtime()}),
                "paquetes": [
                    {
                        "indice": 0,
                        "form": PaquetePedidoForm(prefix="paquete-0"),
                    }
                ],
                "productos_pedido_form": [
                    {
                        "indice": 0,
                        "form": LotePedidoForm(prefix="producto-0"),
                    }
                ],
                "total_paquetes": 1,
                "paquetes_activos": 1,
                "total_productos_pedido": 1,
                "formulario_pedido_abierto": True,
            },
        )

    form = PedidoForm(request.POST)
    total_paquetes = _entero_acotado(
        request.POST.get("package_count"), 1, 1, 20
    )
    total_productos = _entero_acotado(
        request.POST.get("product_count"), 1, 1, 100
    )

    paquetes = []
    for paquete_indice in range(total_paquetes):
        if (
            request.method == "POST"
            and request.POST.get(f"paquete-{paquete_indice}-DELETE") == "1"
        ):
            continue
        paquete_form = PaquetePedidoForm(
            request.POST, prefix=f"paquete-{paquete_indice}"
        )
        paquetes.append(
            {
                "indice": paquete_indice,
                "form": paquete_form,
            }
        )

    productos_pedido_form = []
    for producto_indice in range(total_productos):
        if request.POST.get(f"producto-{producto_indice}-DELETE") == "1":
            continue
        productos_pedido_form.append(
            {
                "indice": producto_indice,
                "form": LotePedidoForm(
                    request.POST,
                    prefix=f"producto-{producto_indice}",
                ),
            }
        )

    formularios_validos = (
        form.is_valid() and bool(paquetes) and bool(productos_pedido_form)
    )
    if not paquetes:
        form.add_error(None, "El pedido debe contener al menos un código de paquete.")
    if not productos_pedido_form:
        form.add_error(None, "El pedido debe contener al menos un producto.")

    codigos = set()
    for paquete in paquetes:
        paquete_valido = paquete["form"].is_valid()
        codigo = paquete["form"].cleaned_data.get("codigo_seguimiento")
        if paquete_valido and codigo:
            if codigo in codigos:
                paquete["form"].add_error(
                    "codigo_seguimiento",
                    "Este código está repetido dentro del pedido.",
                )
                paquete_valido = False
            codigos.add(codigo)
        formularios_validos = formularios_validos and paquete_valido

    for producto_fila in productos_pedido_form:
        formularios_validos = (
            producto_fila["form"].is_valid() and formularios_validos
        )

    if formularios_validos:
        with transaction.atomic():
            pedido = form.save()
            for paquete in paquetes:
                paquete_objeto = paquete["form"].save(commit=False)
                paquete_objeto.pedido = pedido
                paquete_objeto.save()
            for producto_fila in productos_pedido_form:
                lote_objeto = producto_fila["form"].save(commit=False)
                lote_objeto.pedido = pedido
                lote_objeto.save()
        messages.success(
            request, f"Registro de paquetería #{pedido.id} creado correctamente."
        )
        return redirect("negocio:pedido_detalle", pedido_id=pedido.id)

    return pedidos(
        request,
        {
            "form": form,
            "paquetes": paquetes,
            "productos_pedido_form": productos_pedido_form,
            "total_paquetes": total_paquetes,
            "paquetes_activos": len(paquetes),
            "total_productos_pedido": total_productos,
            "formulario_pedido_abierto": True,
        },
    )


def pedido_eliminar(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if request.method == "POST":
        try:
            pedido.delete()
            messages.success(request, f"Registro de paquetería #{pedido_id} eliminado.")
            return redirect("negocio:pedidos")
        except ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar el registro #{pedido_id} porque su inventario ya fue usado en ventas.",
            )
            return redirect("negocio:pedido_detalle", pedido_id=pedido_id)

    return render(
        request,
        "negocio/confirmar_eliminar.html",
        {
            "titulo": f"Eliminar registro de paquetería #{pedido.id}",
            "nombre": pedido.propietario or pedido.cuenta or f"Pedido #{pedido.id}",
            "descripcion": "También se eliminarán sus paquetes y lotes, siempre que no hayan sido usados en ventas.",
            "cancel_url": "negocio:pedido_detalle",
            "cancel_arg": pedido.id,
        },
    )


def pedido_detalle(request, pedido_id):
    get_object_or_404(Pedido, pk=pedido_id)
    return pedidos(request, pedido_abierto=str(pedido_id))


def pedido_producto_recibido_actualizar(request, lote_id):
    lote = get_object_or_404(InventarioLote, pk=lote_id)
    if request.method == "POST":
        form = InventarioRecibidoForm(
            request.POST,
            instance=lote,
            prefix=f"recibido-{lote.id}",
        )
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Recibidos de “{lote.producto.nombre}” actualizados.",
            )
        else:
            messages.error(
                request,
                _primer_error_formulario(
                    form, "No se pudo actualizar la cantidad recibida."
                ),
            )
    return redirect("negocio:pedido_detalle", pedido_id=lote.pedido_id)


def catalogos(request):
    marca_form = MarcaForm(prefix="marca")
    tipo_form = TipoProductoForm(prefix="tipo")
    cliente_form = ClienteForm(prefix="cliente")
    pago_form = TipoPagoForm(prefix="pago")

    if request.method == "POST":
        formulario = request.POST.get("formulario")
        if formulario == "marca":
            marca_form = MarcaForm(request.POST, prefix="marca")
            if marca_form.is_valid():
                marca = marca_form.save()
                messages.success(request, f"Marca “{marca.nombre}” agregada.")
                return redirect("negocio:catalogos")
        elif formulario == "tipo":
            tipo_form = TipoProductoForm(request.POST, prefix="tipo")
            if tipo_form.is_valid():
                tipo = tipo_form.save()
                messages.success(request, f"Tipo “{tipo.nombre}” agregado.")
                return redirect("negocio:catalogos")
        elif formulario == "cliente":
            cliente_form = ClienteForm(request.POST, prefix="cliente")
            if cliente_form.is_valid():
                cliente = cliente_form.save()
                messages.success(request, f"Cliente “{cliente.nombre}” agregado.")
                return redirect("negocio:catalogos")
        elif formulario == "pago":
            pago_form = TipoPagoForm(request.POST, prefix="pago")
            if pago_form.is_valid():
                pago = pago_form.save()
                messages.success(
                    request, f"Método de pago “{pago.nombre}” agregado."
                )
                return redirect("negocio:catalogos")

    return render(
        request,
        "negocio/catalogos.html",
        {
            "marca_form": marca_form,
            "tipo_form": tipo_form,
            "cliente_form": cliente_form,
            "pago_form": pago_form,
            "marcas": Marca.objects.annotate(total_productos=Count("productos")),
            "tipos": TipoProducto.objects.annotate(total_productos=Count("productos")),
            "clientes": Cliente.objects.annotate(total_ventas=Count("ventas")),
            "pagos": TipoPago.objects.annotate(total_ventas=Count("ventas")),
        },
    )


def marca_eliminar(request, marca_id):
    marca = get_object_or_404(Marca, pk=marca_id)
    if request.method == "POST":
        nombre = marca.nombre
        marca.delete()
        messages.success(request, f"Marca “{nombre}” eliminada.")
        return redirect("negocio:catalogos")

    return render(
        request,
        "negocio/confirmar_eliminar.html",
        {
            "titulo": "Eliminar marca",
            "nombre": marca.nombre,
            "descripcion": "Los productos existentes se conservarán, pero quedarán sin marca.",
            "cancel_url": "negocio:catalogos",
        },
    )


def tipo_eliminar(request, tipo_id):
    tipo = get_object_or_404(TipoProducto, pk=tipo_id)
    if request.method == "POST":
        nombre = tipo.nombre
        tipo.delete()
        messages.success(request, f"Tipo “{nombre}” eliminado.")
        return redirect("negocio:catalogos")

    return render(
        request,
        "negocio/confirmar_eliminar.html",
        {
            "titulo": "Eliminar tipo de producto",
            "nombre": tipo.nombre,
            "descripcion": "Los productos existentes se conservarán, pero quedarán sin tipo.",
            "cancel_url": "negocio:catalogos",
        },
    )


def cliente_editar(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    form = ClienteForm(request.POST or None, instance=cliente)
    if request.method == "POST" and form.is_valid():
        cliente = form.save()
        messages.success(request, f"Cliente “{cliente.nombre}” actualizado.")
        return redirect("negocio:catalogos")
    return render(
        request,
        "negocio/catalogo_editar.html",
        {
            "form": form,
            "titulo": "Editar cliente",
            "descripcion": "Actualiza el nombre o teléfono del cliente.",
        },
    )


def cliente_eliminar(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    if request.method == "POST":
        nombre = cliente.nombre
        cliente.delete()
        messages.success(request, f"Cliente “{nombre}” eliminado.")
        return redirect("negocio:catalogos")
    return render(
        request,
        "negocio/confirmar_eliminar.html",
        {
            "titulo": "Eliminar cliente",
            "nombre": cliente.nombre,
            "descripcion": "Las ventas se conservarán, pero quedarán sin cliente asociado.",
            "cancel_url": "negocio:catalogos",
        },
    )


def pago_editar(request, pago_id):
    pago = get_object_or_404(TipoPago, pk=pago_id)
    form = TipoPagoForm(request.POST or None, instance=pago)
    if request.method == "POST" and form.is_valid():
        pago = form.save()
        messages.success(
            request, f"Método de pago “{pago.nombre}” actualizado."
        )
        return redirect("negocio:catalogos")
    return render(
        request,
        "negocio/catalogo_editar.html",
        {
            "form": form,
            "titulo": "Editar método de pago",
            "descripcion": "Cambia el nombre que aparecerá en las ventas.",
        },
    )


def pago_eliminar(request, pago_id):
    pago = get_object_or_404(TipoPago, pk=pago_id)
    if request.method == "POST":
        nombre = pago.nombre
        try:
            pago.delete()
            messages.success(request, f"Método de pago “{nombre}” eliminado.")
        except ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar “{nombre}” porque ya está usado en ventas.",
            )
        return redirect("negocio:catalogos")
    return render(
        request,
        "negocio/confirmar_eliminar.html",
        {
            "titulo": "Eliminar método de pago",
            "nombre": pago.nombre,
            "descripcion": "Solo se puede eliminar si no está utilizado en ninguna venta.",
            "cancel_url": "negocio:catalogos",
        },
    )


def ventas(request, contexto_creacion=None):
    mes = request.GET.get("mes", "")
    tipo_pago_id = request.GET.get("tipo_pago", "")
    orden = request.GET.get("orden", "reciente")

    estadisticas_detalle = (
        DetalleVenta.objects.filter(venta_id=OuterRef("pk"))
        .values("venta_id")
        .annotate(
            unidades_total=Sum("cantidad"),
            venta_bruta=Sum(
                ExpressionWrapper(
                    F("cantidad") * F("precio_unitario_venta"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
        )
    )
    estadisticas_costo = (
        SalidaInventario.objects.filter(detalle_venta__venta_id=OuterRef("pk"))
        .values("detalle_venta__venta_id")
        .annotate(
            costo=Sum(
                ExpressionWrapper(
                    F("cantidad") * F("inventario_lote__costo_unitario_soles"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
        )
    )
    estadisticas_karen = (
        DistribucionGanancia.objects.filter(
            venta_id=OuterRef("pk"), persona__nombre__iexact="Karen"
        )
        .values("venta_id")
        .annotate(total=Sum("monto"))
    )
    costo_por_detalle = (
        SalidaInventario.objects.filter(detalle_venta_id=OuterRef("pk"))
        .values("detalle_venta_id")
        .annotate(
            total=Sum(
                ExpressionWrapper(
                    F("cantidad") * F("inventario_lote__costo_unitario_soles"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
        )
    )
    karen_por_detalle = (
        DistribucionGanancia.objects.filter(
            detalle_venta_id=OuterRef("pk"), persona__nombre__iexact="Karen"
        )
        .values("detalle_venta_id")
        .annotate(total=Sum("monto"))
    )
    detalles_calculados = (
        DetalleVenta.objects.select_related("producto")
        .annotate(
            costo_total=Coalesce(
                Subquery(costo_por_detalle.values("total")),
                Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            comision_karen=Coalesce(
                Subquery(karen_por_detalle.values("total")),
                Value(0),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )
        .order_by("id")
    )

    items = Venta.objects.select_related("cliente", "tipo_pago").prefetch_related(
        Prefetch(
            "detalles", queryset=detalles_calculados, to_attr="detalles_calculados"
        )
    ).annotate(
        unidades=Coalesce(
            Subquery(estadisticas_detalle.values("unidades_total")),
            Value(0),
            output_field=IntegerField(),
        ),
        subtotal=Coalesce(
            Subquery(estadisticas_detalle.values("venta_bruta")),
            Value(0),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        costo_total=Coalesce(
            Subquery(estadisticas_costo.values("costo")),
            Value(0),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        monto_karen=Coalesce(
            Subquery(estadisticas_karen.values("total")),
            Value(0),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    )
    items = items.annotate(
        total=F("subtotal") - F("descuento"),
        mi_ganancia=F("subtotal")
        - F("descuento")
        - F("costo_total")
        - F("monto_karen"),
    )

    if mes:
        try:
            year, month = (int(part) for part in mes.split("-", 1))
            if 1 <= month <= 12:
                items = items.annotate(
                    venta_year=ExtractYear("fecha"), venta_month=ExtractMonth("fecha")
                ).filter(venta_year=year, venta_month=month)
        except (TypeError, ValueError):
            mes = ""
    if tipo_pago_id.isdigit():
        items = items.filter(tipo_pago_id=tipo_pago_id)

    items = items.order_by("fecha" if orden == "antigua" else "-fecha")

    centimo = Decimal("0.01")
    for venta in items:
        descuento_restante = venta.descuento
        detalles = venta.detalles_calculados
        for detalle in detalles:
            detalle.precio_venta_total = (
                Decimal(detalle.cantidad) * detalle.precio_unitario_venta
            )
            detalle.margen_antes_descuento = (
                detalle.precio_venta_total
                - detalle.costo_total
                - detalle.comision_karen
            )
        detalles_con_margen = [
            detalle for detalle in detalles if detalle.margen_antes_descuento > 0
        ]
        margen_disponible = sum(
            (detalle.margen_antes_descuento for detalle in detalles_con_margen),
            Decimal("0"),
        )
        for detalle in detalles:
            if detalle not in detalles_con_margen:
                detalle.descuento_asignado = Decimal("0")
            elif detalle is detalles_con_margen[-1]:
                detalle.descuento_asignado = descuento_restante
            elif margen_disponible:
                detalle.descuento_asignado = (
                    venta.descuento
                    * detalle.margen_antes_descuento
                    / margen_disponible
                ).quantize(centimo, rounding=ROUND_HALF_UP)
                descuento_restante -= detalle.descuento_asignado
            else:
                detalle.descuento_asignado = Decimal("0")
            detalle.mi_ganancia = (
                detalle.margen_antes_descuento - detalle.descuento_asignado
            )
            if not venta.cerrada:
                detalle.form_edicion = DetalleVentaForm(
                    instance=detalle, prefix=f"detalle-{detalle.id}"
                )
        if not venta.cerrada:
            venta.form_edicion = VentaEditarForm(
                instance=venta, prefix=f"venta-{venta.id}"
            )
            venta.form_producto_nuevo = DetalleVentaForm(prefix=f"nuevo-{venta.id}")
    resumen = {
        "costo_total": sum(
            (venta.costo_total for venta in items), Decimal("0")
        ),
        "precio_venta_total": sum(
            (venta.total for venta in items), Decimal("0")
        ),
        "comision_karen_total": sum(
            (venta.monto_karen for venta in items), Decimal("0")
        ),
        "mi_ganancia_total": sum(
            (venta.mi_ganancia for venta in items), Decimal("0")
        ),
    }

    if contexto_creacion is None:
        contexto_creacion = {
            "venta_crear_form": VentaForm(
                initial={
                    "fecha": timezone.localtime(),
                    "estado_entrega": "No entregado",
                }
            ),
            "detalles_crear": [
                {"indice": 0, "form": DetalleVentaForm(prefix="detalle-0")}
            ],
            "total_detalles": 1,
            "formulario_venta_abierto": request.GET.get("crear") == "1",
        }
    contexto_creacion["lotes_disponibles"] = lotes_con_stock()

    return render(
        request,
        "negocio/ventas.html",
        {
            "ventas": items,
            "tipos_pago": TipoPago.objects.all(),
            "mes_seleccionado": mes,
            "pago_seleccionado": tipo_pago_id,
            "orden_seleccionado": orden,
            "resumen": resumen,
            "venta_abierta": request.GET.get("abierta", ""),
            **contexto_creacion,
        },
    )


def venta_crear(request):
    if request.method != "POST":
        return ventas(
            request,
            {
                "venta_crear_form": VentaForm(
                    initial={
                        "fecha": timezone.localtime(),
                        "estado_entrega": "No entregado",
                    }
                ),
                "detalles_crear": [
                    {"indice": 0, "form": DetalleVentaForm(prefix="detalle-0")}
                ],
                "total_detalles": 1,
                "formulario_venta_abierto": True,
            },
        )

    if request.method == "POST":
        form = VentaForm(request.POST)
        total_detalles = _entero_acotado(
            request.POST.get("detalle_count"), 1, 1, 50
        )
    else:
        form = VentaForm(
            initial={
                "fecha": timezone.localtime(),
                "estado_entrega": "No entregado",
            }
        )
        total_detalles = 1

    detalles = []
    for indice in range(total_detalles):
        if (
            request.method == "POST"
            and request.POST.get(f"detalle-{indice}-DELETE") == "1"
        ):
            continue
        detalles.append(
            {
                "indice": indice,
                "form": DetalleVentaForm(
                    request.POST or None, prefix=f"detalle-{indice}"
                ),
            }
        )

    if request.method == "POST":
        valido = form.is_valid() and bool(detalles)
        if not detalles:
            form.add_error(None, "La venta debe contener al menos un producto.")

        cantidades_por_lote = {}
        formularios_por_lote = {}
        margen_total = Decimal("0")
        for detalle_fila in detalles:
            detalle_form = detalle_fila["form"]
            valido_detalle = detalle_form.is_valid()
            valido = valido and valido_detalle
            if valido_detalle:
                margen_detalle = _validar_detalle_sin_perdida(detalle_form)
                if margen_detalle is None:
                    valido = False
                else:
                    margen_total += margen_detalle
                lote = detalle_form.cleaned_data["inventario_lote"]
                cantidades_por_lote[lote.id] = (
                    cantidades_por_lote.get(lote.id, 0)
                    + detalle_form.cleaned_data["cantidad"]
                )
                formularios_por_lote.setdefault(lote.id, []).append(detalle_form)

        if valido:
            lotes = {lote.id: lote for lote in lotes_con_stock()}
            for lote_id, cantidad_solicitada in cantidades_por_lote.items():
                lote = lotes.get(lote_id)
                disponible = lote.stock_disponible if lote else 0
                if cantidad_solicitada > disponible:
                    for detalle_form in formularios_por_lote[lote_id]:
                        detalle_form.add_error(
                            "cantidad",
                            f"Entre todas las líneas solicitaste "
                            f"{cantidad_solicitada}, pero este lote tiene "
                            f"{disponible} disponibles.",
                        )
                    valido = False

        if valido and form.cleaned_data["descuento"] > margen_total:
            form.add_error(
                "descuento",
                f"El descuento máximo para no tener pérdidas es S/{margen_total:.2f}.",
            )
            valido = False

        if valido:
            with transaction.atomic():
                venta = form.save()
                persona_karen, _ = PersonaGanancia.objects.get_or_create(
                    nombre="Karen"
                )
                for detalle_fila in detalles:
                    detalle_form = detalle_fila["form"]
                    lote = detalle_form.cleaned_data["inventario_lote"]
                    detalle = detalle_form.save(commit=False)
                    detalle.venta = venta
                    detalle.producto = lote.producto
                    detalle.save()
                    SalidaInventario.objects.create(
                        detalle_venta=detalle,
                        inventario_lote=lote,
                        cantidad=detalle.cantidad,
                    )
                    DistribucionGanancia.objects.create(
                        venta=venta,
                        detalle_venta=detalle,
                        persona=persona_karen,
                        monto=detalle_form.cleaned_data.get("comision_karen") or 0,
                    )

            messages.success(request, f"Venta #{venta.id} registrada correctamente.")
            return redirect("negocio:ventas")

    return ventas(
        request,
        {
            "venta_crear_form": form,
            "detalles_crear": detalles,
            "total_detalles": total_detalles,
            "formulario_venta_abierto": True,
        },
    )


def venta_editar(request, venta_id):
    venta = get_object_or_404(Venta, pk=venta_id)
    if venta.cerrada:
        messages.error(request, f"La venta #{venta.id} está cerrada y ya no se puede editar.")
        return redirect(f"{reverse('negocio:ventas')}?abierta={venta.id}")
    if request.method == "POST":
        form = VentaEditarForm(
            request.POST, instance=venta, prefix=f"venta-{venta.id}"
        )
        if form.is_valid():
            margen_total, _ = _margen_venta_actual(venta)
            if form.cleaned_data["descuento"] > margen_total:
                messages.error(
                    request,
                    f"El descuento máximo para no tener pérdidas es S/{max(margen_total, Decimal('0')):.2f}.",
                )
            else:
                form.save()
                messages.success(request, f"Venta #{venta.id} actualizada.")
        else:
            messages.error(request, "No se pudo actualizar la venta. Revisa los datos.")
    return redirect(f"{reverse('negocio:ventas')}?abierta={venta.id}")


def venta_cerrar(request, venta_id):
    venta = get_object_or_404(Venta, pk=venta_id)
    if request.method == "POST":
        if venta.cerrada:
            messages.info(request, f"La venta #{venta.id} ya estaba cerrada.")
        else:
            margen_total, hay_linea_negativa = _margen_venta_actual(venta)
            if hay_linea_negativa or margen_total < venta.descuento:
                messages.error(
                    request,
                    "No se puede cerrar la venta porque genera una pérdida. "
                    "Corrige los precios, la comisión o el descuento.",
                )
            else:
                venta.cerrada = True
                venta.fecha_cierre = timezone.now()
                venta.save(update_fields=["cerrada", "fecha_cierre"])
                messages.success(
                    request,
                    f"Venta #{venta.id} cerrada. Quedó guardada como registro.",
                )
    return redirect(f"{reverse('negocio:ventas')}?abierta={venta.id}")


def venta_producto_agregar(request, venta_id):
    venta = get_object_or_404(Venta, pk=venta_id)
    if venta.cerrada:
        messages.error(request, f"La venta #{venta.id} está cerrada y ya no acepta productos.")
        return redirect(f"{reverse('negocio:ventas')}?abierta={venta.id}")
    if request.method == "POST":
        form = DetalleVentaForm(request.POST, prefix=f"nuevo-{venta.id}")
        if form.is_valid():
            margen_detalle = _validar_detalle_sin_perdida(form)
            margen_actual, _ = _margen_venta_actual(venta)
            if (
                margen_detalle is not None
                and margen_actual + margen_detalle >= venta.descuento
            ):
                with transaction.atomic():
                    lote = form.cleaned_data["inventario_lote"]
                    detalle = form.save(commit=False)
                    detalle.venta = venta
                    detalle.producto = lote.producto
                    detalle.save()
                    SalidaInventario.objects.create(
                        detalle_venta=detalle,
                        inventario_lote=lote,
                        cantidad=detalle.cantidad,
                    )
                    persona_karen, _ = PersonaGanancia.objects.get_or_create(
                        nombre="Karen"
                    )
                    DistribucionGanancia.objects.create(
                        venta=venta,
                        detalle_venta=detalle,
                        persona=persona_karen,
                        monto=form.cleaned_data.get("comision_karen") or 0,
                    )
                messages.success(request, "Producto agregado a la venta.")
            elif margen_detalle is not None:
                form.add_error(
                    "precio_unitario_venta",
                    "La venta completa quedaría con ganancia negativa.",
                )
        if form.errors:
            messages.error(
                request,
                _primer_error_formulario(form, "Revisa los datos del producto."),
            )
    return redirect(f"{reverse('negocio:ventas')}?abierta={venta.id}")


def detalle_venta_editar(request, detalle_id):
    detalle = get_object_or_404(
        DetalleVenta.objects.select_related("venta"), pk=detalle_id
    )
    if detalle.venta.cerrada:
        messages.error(
            request,
            f"La venta #{detalle.venta_id} está cerrada y ya no se puede editar.",
        )
        return redirect(f"{reverse('negocio:ventas')}?abierta={detalle.venta_id}")
    if request.method == "POST":
        form = DetalleVentaForm(
            request.POST,
            instance=detalle,
            prefix=f"detalle-{detalle.id}",
        )
        if form.is_valid():
            margen_detalle = _validar_detalle_sin_perdida(form)
            margen_restante, _ = _margen_venta_actual(
                detalle.venta, omitir_detalle_id=detalle.id
            )
            if (
                margen_detalle is not None
                and margen_restante + margen_detalle >= detalle.venta.descuento
            ):
                with transaction.atomic():
                    lote = form.cleaned_data["inventario_lote"]
                    detalle = form.save(commit=False)
                    detalle.producto = lote.producto
                    detalle.save()
                    detalle.salidas.all().delete()
                    SalidaInventario.objects.create(
                        detalle_venta=detalle,
                        inventario_lote=lote,
                        cantidad=detalle.cantidad,
                    )
                    persona_karen, _ = PersonaGanancia.objects.get_or_create(
                        nombre="Karen"
                    )
                    DistribucionGanancia.objects.update_or_create(
                        detalle_venta=detalle,
                        persona=persona_karen,
                        defaults={
                            "venta": detalle.venta,
                            "monto": form.cleaned_data.get("comision_karen") or 0,
                        },
                    )
                messages.success(request, "Producto actualizado.")
            elif margen_detalle is not None:
                form.add_error(
                    "precio_unitario_venta",
                    "La venta completa quedaría con ganancia negativa.",
                )
        if form.errors:
            messages.error(
                request,
                _primer_error_formulario(form, "Revisa los datos del producto."),
            )
    return redirect(f"{reverse('negocio:ventas')}?abierta={detalle.venta_id}")
