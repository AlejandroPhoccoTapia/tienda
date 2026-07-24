from datetime import datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Cliente,
    DetalleVenta,
    DistribucionGanancia,
    InventarioLote,
    Marca,
    Paquete,
    Pedido,
    Producto,
    SalidaInventario,
    TipoPago,
    TipoProducto,
    Venta,
)


class VistasNegocioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.marca_a = Marca.objects.create(nombre="Marca A")
        cls.marca_b = Marca.objects.create(nombre="Marca B")
        cls.tipo_a = TipoProducto.objects.create(nombre="Tipo A")
        cls.tipo_b = TipoProducto.objects.create(nombre="Tipo B")
        cls.producto_a = Producto.objects.create(
            nombre="Producto A", marca=cls.marca_a, tipo_producto=cls.tipo_a
        )
        cls.producto_b = Producto.objects.create(
            nombre="Producto B", marca=cls.marca_b, tipo_producto=cls.tipo_b
        )
        cls.pedido = Pedido.objects.create(
            cuenta="Cuenta",
            propietario="Propietario",
            direccion="Dirección",
            fecha=timezone.make_aware(datetime(2026, 7, 2, 10, 0)),
        )
        cls.paquete = Paquete.objects.create(
            pedido=cls.pedido, codigo_seguimiento="ABC", entregado=True
        )
        cls.lote = InventarioLote.objects.create(
            paquete=cls.paquete,
            producto=cls.producto_a,
            cantidad_inicial=10,
            costo_unitario_soles=Decimal("20.00"),
        )
        cls.yape = TipoPago.objects.create(nombre="Yape")
        cls.efectivo = TipoPago.objects.create(nombre="Efectivo")
        cls.cliente = Cliente.objects.create(nombre="Cliente")
        cls.venta_julio = Venta.objects.create(
            fecha=timezone.make_aware(datetime(2026, 7, 3, 10, 0)),
            cliente=cls.cliente,
            tipo_pago=cls.yape,
            estado_entrega="Entregado",
            pagado=True,
        )
        cls.detalle = DetalleVenta.objects.create(
            venta=cls.venta_julio,
            producto=cls.producto_a,
            cantidad=3,
            precio_unitario_venta=Decimal("35.00"),
        )
        SalidaInventario.objects.create(
            detalle_venta=cls.detalle, inventario_lote=cls.lote, cantidad=3
        )
        cls.venta_junio = Venta.objects.create(
            fecha=timezone.make_aware(datetime(2026, 6, 1, 10, 0)),
            cliente=cls.cliente,
            tipo_pago=cls.efectivo,
            estado_entrega="Pendiente",
        )

    def test_productos_filtra_marca_y_tipo_y_calcula_stock(self):
        pedido_pendiente = Pedido.objects.create(
            cuenta="Pendiente",
            fecha=timezone.make_aware(datetime(2026, 7, 20, 10, 0)),
        )
        paquete_pendiente = Paquete.objects.create(
            pedido=pedido_pendiente,
            codigo_seguimiento="PENDIENTE-01",
            entregado=False,
        )
        InventarioLote.objects.create(
            paquete=paquete_pendiente,
            producto=self.producto_a,
            cantidad_inicial=25,
            costo_unitario_soles=Decimal("18.00"),
        )
        response = self.client.get(
            reverse("negocio:productos"),
            {"marca": self.marca_a.id, "tipo": self.tipo_a.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Producto A")
        self.assertNotContains(response, "Producto B")
        self.assertEqual(list(response.context["productos"])[0].stock, 7)

    def test_listado_y_detalle_de_pedido(self):
        listado = self.client.get(reverse("negocio:pedidos"))
        detalle = self.client.get(
            reverse("negocio:pedido_detalle", args=[self.pedido.id])
        )
        self.assertContains(listado, "Propietario")
        self.assertContains(detalle, "ABC")
        self.assertContains(detalle, "Producto A")

    def test_ventas_filtra_mes_y_pago(self):
        response = self.client.get(
            reverse("negocio:ventas"),
            {"mes": "2026-07", "tipo_pago": self.yape.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"#{self.venta_julio.id}")
        self.assertNotContains(response, f"#{self.venta_junio.id}")

    def test_ventas_orden_antiguo(self):
        response = self.client.get(reverse("negocio:ventas"), {"orden": "antigua"})
        ids = list(response.context["ventas"].values_list("id", flat=True))
        self.assertEqual(ids, [self.venta_junio.id, self.venta_julio.id])

    def test_crea_pedido_desde_formulario(self):
        response = self.client.post(
            reverse("negocio:pedido_crear"),
            {
                "cuenta": "Cuenta nueva",
                "propietario": "Diego",
                "direccion": "Lima",
                "fecha": "2026-07-24T15:30",
                "descuento": "5.00",
                "dolar_valor": "3.7500",
                "package_count": "1",
                "paquete-0-codigo_seguimiento": "NUEVO-001",
                "paquete-0-entregado": "",
                "paquete-0-fecha_entrega": "",
                "lote-0-count": "1",
                "lote-0-0-producto": self.producto_b.id,
                "lote-0-0-cantidad_inicial": "4",
                "lote-0-0-costo_unitario_dolar": "12.50",
                "lote-0-0-costo_unitario_soles": "46.88",
                "lote-0-0-costo_soles_manual": "on",
            },
        )
        pedido = Pedido.objects.get(cuenta="Cuenta nueva")
        self.assertRedirects(
            response, reverse("negocio:pedido_detalle", args=[pedido.id])
        )
        self.assertEqual(pedido.propietario, "Diego")
        self.assertEqual(pedido.paquetes.count(), 1)
        self.assertEqual(pedido.paquetes.get().lotes.get().cantidad_inicial, 4)

    def test_crea_pedido_con_varios_paquetes(self):
        data = {
            "cuenta": "Compra dividida",
            "propietario": "Diego",
            "direccion": "Lima",
            "fecha": "2026-07-24T15:30",
            "descuento": "0",
            "dolar_valor": "3.7500",
            "package_count": "2",
        }
        for indice, producto in enumerate([self.producto_a, self.producto_b]):
            data.update(
                {
                    f"paquete-{indice}-codigo_seguimiento": f"PACK-{indice}",
                    f"paquete-{indice}-fecha_entrega": "",
                    f"lote-{indice}-count": "1",
                    f"lote-{indice}-0-producto": producto.id,
                    f"lote-{indice}-0-cantidad_inicial": "2",
                    f"lote-{indice}-0-costo_unitario_dolar": "10.00",
                    f"lote-{indice}-0-costo_unitario_soles": "37.50",
                    f"lote-{indice}-0-costo_soles_manual": "on",
                }
            )
        response = self.client.post(reverse("negocio:pedido_crear"), data)
        pedido = Pedido.objects.get(cuenta="Compra dividida")
        self.assertRedirects(
            response, reverse("negocio:pedido_detalle", args=[pedido.id])
        )
        self.assertEqual(pedido.paquetes.count(), 2)
        self.assertEqual(InventarioLote.objects.filter(paquete__pedido=pedido).count(), 2)

    def test_agrega_marca_y_tipo_desde_catalogos(self):
        marca_response = self.client.post(
            reverse("negocio:catalogos"),
            {"formulario": "marca", "marca-nombre": "Marca nueva"},
        )
        tipo_response = self.client.post(
            reverse("negocio:catalogos"),
            {"formulario": "tipo", "tipo-nombre": "Tipo nuevo"},
        )
        self.assertRedirects(marca_response, reverse("negocio:catalogos"))
        self.assertRedirects(tipo_response, reverse("negocio:catalogos"))
        self.assertTrue(Marca.objects.filter(nombre="Marca nueva").exists())
        self.assertTrue(TipoProducto.objects.filter(nombre="Tipo nuevo").exists())

    def test_no_permite_marca_duplicada(self):
        response = self.client.post(
            reverse("negocio:catalogos"),
            {"formulario": "marca", "marca-nombre": self.marca_a.nombre},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe")
        self.assertEqual(Marca.objects.filter(nombre=self.marca_a.nombre).count(), 1)

    def test_crea_producto_desde_formulario(self):
        imagen = SimpleUploadedFile(
            "producto.gif",
            (
                b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00"
                b"\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00"
                b"\x00\x02\x02D\x01\x00;"
            ),
            content_type="image/gif",
        )
        response = self.client.post(
            reverse("negocio:producto_crear"),
            {
                "nombre": "Producto nuevo",
                "marca": self.marca_a.id,
                "tipo_producto": self.tipo_a.id,
                "link": "https://example.com/producto",
                "foto": imagen,
            },
        )
        self.assertRedirects(response, reverse("negocio:productos"))
        producto = Producto.objects.get(nombre="Producto nuevo")
        self.assertEqual(producto.marca, self.marca_a)
        self.assertEqual(producto.tipo_producto, self.tipo_a)
        self.assertTrue(producto.foto.name.startswith("productos/"))
        producto.foto.delete(save=False)

    def test_elimina_producto_sin_movimientos(self):
        producto = Producto.objects.create(
            nombre="Descartable", marca=self.marca_a, tipo_producto=self.tipo_a
        )
        response = self.client.post(
            reverse("negocio:producto_eliminar", args=[producto.id])
        )
        self.assertRedirects(response, reverse("negocio:productos"))
        self.assertFalse(Producto.objects.filter(pk=producto.id).exists())

    def test_protege_producto_con_inventario_o_ventas(self):
        response = self.client.post(
            reverse("negocio:producto_eliminar", args=[self.producto_a.id])
        )
        self.assertRedirects(response, reverse("negocio:productos"))
        self.assertTrue(Producto.objects.filter(pk=self.producto_a.id).exists())

    def test_elimina_marca_y_conserva_producto(self):
        response = self.client.post(
            reverse("negocio:marca_eliminar", args=[self.marca_b.id])
        )
        self.assertRedirects(response, reverse("negocio:catalogos"))
        self.producto_b.refresh_from_db()
        self.assertIsNone(self.producto_b.marca)

    def test_elimina_tipo_y_conserva_producto(self):
        response = self.client.post(
            reverse("negocio:tipo_eliminar", args=[self.tipo_b.id])
        )
        self.assertRedirects(response, reverse("negocio:catalogos"))
        self.producto_b.refresh_from_db()
        self.assertIsNone(self.producto_b.tipo_producto)

    def test_elimina_pedido_sin_inventario_usado(self):
        pedido = Pedido.objects.create(
            cuenta="Temporal",
            fecha=timezone.make_aware(datetime(2026, 7, 20, 10, 0)),
        )
        response = self.client.post(
            reverse("negocio:pedido_eliminar", args=[pedido.id])
        )
        self.assertRedirects(response, reverse("negocio:pedidos"))
        self.assertFalse(Pedido.objects.filter(pk=pedido.id).exists())

    def test_protege_pedido_cuyo_inventario_fue_vendido(self):
        response = self.client.post(
            reverse("negocio:pedido_eliminar", args=[self.pedido.id])
        )
        self.assertRedirects(
            response, reverse("negocio:pedido_detalle", args=[self.pedido.id])
        )
        self.assertTrue(Pedido.objects.filter(pk=self.pedido.id).exists())

    def test_registra_venta_y_descuenta_inventario_fifo(self):
        response = self.client.post(
            reverse("negocio:venta_crear"),
            {
                "fecha": "2026-07-24T16:00",
                "cliente": self.cliente.id,
                "tipo_pago": self.yape.id,
                "direccion_entrega": "Miraflores",
                "descuento": "5.00",
                "monto_karen": "10.00",
                "pagado": "on",
                "estado_entrega": "No entregado",
                "detalle_count": "1",
                "detalle-0-inventario_lote": self.lote.id,
                "detalle-0-cantidad": "2",
                "detalle-0-precio_unitario_venta": "40.00",
            },
        )
        self.assertRedirects(response, reverse("negocio:ventas"))
        venta = Venta.objects.get(direccion_entrega="Miraflores")
        detalle = venta.detalles.get()
        self.assertEqual(detalle.cantidad, 2)
        self.assertEqual(detalle.salidas.aggregate(total=Sum("cantidad"))["total"], 2)
        self.assertEqual(
            DistribucionGanancia.objects.get(
                venta=venta, persona__nombre="Karen"
            ).monto,
            Decimal("10.00"),
        )
        venta_calculada = self.client.get(reverse("negocio:ventas")).context[
            "ventas"
        ].get(pk=venta.id)
        self.assertEqual(venta_calculada.costo_total, Decimal("40"))
        self.assertEqual(venta_calculada.total, Decimal("75"))
        self.assertEqual(venta_calculada.monto_karen, Decimal("10"))
        self.assertEqual(venta_calculada.mi_ganancia, Decimal("25"))

    def test_no_registra_venta_sin_stock_suficiente(self):
        response = self.client.post(
            reverse("negocio:venta_crear"),
            {
                "fecha": "2026-07-24T16:00",
                "cliente": self.cliente.id,
                "tipo_pago": self.yape.id,
                "direccion_entrega": "Venta imposible",
                "descuento": "0",
                "estado_entrega": "No entregado",
                "detalle_count": "1",
                "detalle-0-inventario_lote": self.lote.id,
                "detalle-0-cantidad": "99",
                "detalle-0-precio_unitario_venta": "40.00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Solo hay 7 unidades disponibles")
        self.assertFalse(Venta.objects.filter(direccion_entrega="Venta imposible").exists())

    def test_selector_de_venta_muestra_lote_costo_y_stock(self):
        response = self.client.get(reverse("negocio:venta_crear"))
        self.assertContains(response, "Producto A")
        self.assertContains(response, f"Lote #{self.lote.id}")
        self.assertContains(response, "Costo S/ 20.00")
        self.assertContains(response, "Disponible: 7")

    def test_selector_de_venta_excluye_lotes_no_entregados(self):
        pedido = Pedido.objects.create(
            cuenta="Aún viajando",
            fecha=timezone.make_aware(datetime(2026, 7, 21, 10, 0)),
        )
        paquete = Paquete.objects.create(
            pedido=pedido, codigo_seguimiento="VIAJANDO-99", entregado=False
        )
        lote_pendiente = InventarioLote.objects.create(
            paquete=paquete,
            producto=self.producto_b,
            cantidad_inicial=10,
            costo_unitario_soles=Decimal("25.00"),
        )
        response = self.client.get(reverse("negocio:venta_crear"))
        self.assertNotContains(response, f"Lote #{lote_pendiente.id}")
        self.assertNotContains(response, "VIAJANDO-99")

    def test_no_permite_superar_stock_repartiendo_el_mismo_lote(self):
        response = self.client.post(
            reverse("negocio:venta_crear"),
            {
                "fecha": "2026-07-24T16:00",
                "cliente": self.cliente.id,
                "tipo_pago": self.yape.id,
                "direccion_entrega": "Venta doble imposible",
                "descuento": "0",
                "estado_entrega": "No entregado",
                "detalle_count": "2",
                "detalle-0-inventario_lote": self.lote.id,
                "detalle-0-cantidad": "4",
                "detalle-0-precio_unitario_venta": "40.00",
                "detalle-1-inventario_lote": self.lote.id,
                "detalle-1-cantidad": "4",
                "detalle-1-precio_unitario_venta": "40.00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "solicitaste 8")
        self.assertFalse(
            Venta.objects.filter(direccion_entrega="Venta doble imposible").exists()
        )

    def test_crea_cliente_y_metodo_pago_desde_catalogos(self):
        cliente_response = self.client.post(
            reverse("negocio:catalogos"),
            {
                "formulario": "cliente",
                "cliente-nombre": "Cliente nuevo",
                "cliente-telefono": "900 111 222",
            },
        )
        pago_response = self.client.post(
            reverse("negocio:catalogos"),
            {"formulario": "pago", "pago-nombre": "Plin"},
        )
        self.assertRedirects(cliente_response, reverse("negocio:catalogos"))
        self.assertRedirects(pago_response, reverse("negocio:catalogos"))
        self.assertTrue(Cliente.objects.filter(nombre="Cliente nuevo").exists())
        self.assertTrue(TipoPago.objects.filter(nombre="Plin").exists())

    def test_edita_cliente_y_metodo_pago(self):
        cliente_response = self.client.post(
            reverse("negocio:cliente_editar", args=[self.cliente.id]),
            {"nombre": "Cliente actualizado", "telefono": "955 000 111"},
        )
        pago = TipoPago.objects.create(nombre="Tarjeta")
        pago_response = self.client.post(
            reverse("negocio:pago_editar", args=[pago.id]),
            {"nombre": "Tarjeta POS"},
        )
        self.assertRedirects(cliente_response, reverse("negocio:catalogos"))
        self.assertRedirects(pago_response, reverse("negocio:catalogos"))
        self.cliente.refresh_from_db()
        pago.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Cliente actualizado")
        self.assertEqual(pago.nombre, "Tarjeta POS")

    def test_elimina_cliente_y_conserva_sus_ventas(self):
        venta_id = self.venta_julio.id
        response = self.client.post(
            reverse("negocio:cliente_eliminar", args=[self.cliente.id])
        )
        self.assertRedirects(response, reverse("negocio:catalogos"))
        self.assertFalse(Cliente.objects.filter(pk=self.cliente.id).exists())
        self.assertIsNone(Venta.objects.get(pk=venta_id).cliente)

    def test_protege_metodo_pago_utilizado(self):
        response = self.client.post(
            reverse("negocio:pago_eliminar", args=[self.yape.id])
        )
        self.assertRedirects(response, reverse("negocio:catalogos"))
        self.assertTrue(TipoPago.objects.filter(pk=self.yape.id).exists())

    def test_elimina_metodo_pago_sin_ventas(self):
        pago = TipoPago.objects.create(nombre="Cheque")
        response = self.client.post(
            reverse("negocio:pago_eliminar", args=[pago.id])
        )
        self.assertRedirects(response, reverse("negocio:catalogos"))
        self.assertFalse(TipoPago.objects.filter(pk=pago.id).exists())
