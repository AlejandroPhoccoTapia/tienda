from decimal import Decimal, ROUND_HALF_UP

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
from django.utils import timezone

from .forms import (
    ClienteForm,
    DetalleVentaForm,
    LotePedidoForm,
    MarcaForm,
    PaquetePedidoForm,
    PedidoForm,
    ProductoForm,
    TipoProductoForm,
    TipoPagoForm,
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


def productos(request):
    marca_id = request.GET.get("marca", "")
    tipo_id = request.GET.get("tipo", "")

    entradas = (
        InventarioLote.objects.filter(
            producto_id=OuterRef("pk"), paquete__entregado=True
        )
        .values("producto_id")
        .annotate(total=Sum("cantidad_inicial"))
        .values("total")
    )
    salidas = (
        SalidaInventario.objects.filter(
            inventario_lote__producto_id=OuterRef("pk"),
            inventario_lote__paquete__entregado=True,
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


def pedidos(request):
    items = Pedido.objects.annotate(
        total_paquetes=Count("paquetes", distinct=True),
        paquetes_entregados=Count(
            "paquetes", filter=Q(paquetes__entregado=True), distinct=True
        ),
        total_unidades=Coalesce(
            Sum("paquetes__lotes__cantidad_inicial"),
            Value(0),
            output_field=IntegerField(),
        ),
    )
    return render(request, "negocio/pedidos.html", {"pedidos": items})


def pedido_crear(request):
    if request.method == "POST":
        form = PedidoForm(request.POST)
        total_paquetes = _entero_acotado(request.POST.get("package_count"), 1, 1, 20)
    else:
        form = PedidoForm(initial={"fecha": timezone.localtime()})
        total_paquetes = 1

    paquetes = []
    for paquete_indice in range(total_paquetes):
        if (
            request.method == "POST"
            and request.POST.get(f"paquete-{paquete_indice}-DELETE") == "1"
        ):
            continue
        paquete_form = PaquetePedidoForm(
            request.POST or None, prefix=f"paquete-{paquete_indice}"
        )
        total_lotes = (
            _entero_acotado(
                request.POST.get(f"lote-{paquete_indice}-count"), 1, 1, 50
            )
            if request.method == "POST"
            else 1
        )
        lotes = []
        for lote_indice in range(total_lotes):
            if (
                request.method == "POST"
                and request.POST.get(
                    f"lote-{paquete_indice}-{lote_indice}-DELETE"
                )
                == "1"
            ):
                continue
            lotes.append(
                {
                    "indice": lote_indice,
                    "form": LotePedidoForm(
                        request.POST or None,
                        prefix=f"lote-{paquete_indice}-{lote_indice}",
                    ),
                }
            )
        paquetes.append(
            {
                "indice": paquete_indice,
                "form": paquete_form,
                "lotes": lotes,
                "total_lotes": total_lotes,
            }
        )

    if request.method == "POST":
        formularios_validos = form.is_valid() and bool(paquetes)
        if not paquetes:
            form.add_error(None, "El pedido debe contener al menos un paquete.")
        codigos = set()
        for paquete in paquetes:
            paquete_valido = paquete["form"].is_valid()
            lotes_validos = bool(paquete["lotes"])
            if not paquete["lotes"]:
                paquete["form"].add_error(
                    None, "Cada paquete debe contener al menos un producto."
                )
            for lote in paquete["lotes"]:
                lotes_validos = lote["form"].is_valid() and lotes_validos
            codigo = paquete["form"].cleaned_data.get("codigo_seguimiento")
            if paquete_valido and codigo:
                if codigo in codigos:
                    paquete["form"].add_error(
                        "codigo_seguimiento",
                        "Este código está repetido dentro del pedido.",
                    )
                    paquete_valido = False
                codigos.add(codigo)
            formularios_validos = (
                formularios_validos and paquete_valido and lotes_validos
            )

        if formularios_validos:
            with transaction.atomic():
                pedido = form.save()
                for paquete in paquetes:
                    paquete_objeto = paquete["form"].save(commit=False)
                    paquete_objeto.pedido = pedido
                    paquete_objeto.save()
                    for lote_fila in paquete["lotes"]:
                        lote_objeto = lote_fila["form"].save(commit=False)
                        lote_objeto.paquete = paquete_objeto
                        lote_objeto.save()
            messages.success(
                request, f"Registro de paquetería #{pedido.id} creado correctamente."
            )
            return redirect("negocio:pedido_detalle", pedido_id=pedido.id)

    return render(
        request,
        "negocio/pedido_form.html",
        {
            "form": form,
            "paquetes": paquetes,
            "total_paquetes": total_paquetes,
            "paquetes_activos": len(paquetes),
            "productos_disponibles": Producto.objects.all(),
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
    pedido = get_object_or_404(
        Pedido.objects.prefetch_related(
            "paquetes__lotes__producto__marca",
            "paquetes__lotes__producto__tipo_producto",
        ),
        pk=pedido_id,
    )
    return render(request, "negocio/pedido_detalle.html", {"pedido": pedido})


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


def ventas(request):
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
        for indice, detalle in enumerate(detalles):
            detalle.precio_venta_total = (
                Decimal(detalle.cantidad) * detalle.precio_unitario_venta
            )
            if indice == len(detalles) - 1:
                detalle.descuento_asignado = descuento_restante
            elif venta.subtotal:
                detalle.descuento_asignado = (
                    venta.descuento
                    * detalle.precio_venta_total
                    / venta.subtotal
                ).quantize(centimo, rounding=ROUND_HALF_UP)
                descuento_restante -= detalle.descuento_asignado
            else:
                detalle.descuento_asignado = Decimal("0")
            detalle.mi_ganancia = (
                detalle.precio_venta_total
                - detalle.descuento_asignado
                - detalle.costo_total
                - detalle.comision_karen
            )
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
        },
    )


def venta_crear(request):
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
        for detalle_fila in detalles:
            detalle_form = detalle_fila["form"]
            valido_detalle = detalle_form.is_valid()
            valido = valido and valido_detalle
            if valido_detalle:
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

    return render(
        request,
        "negocio/venta_form.html",
        {
            "form": form,
            "detalles": detalles,
            "total_detalles": total_detalles,
            "lotes_disponibles": lotes_con_stock(),
        },
    )
