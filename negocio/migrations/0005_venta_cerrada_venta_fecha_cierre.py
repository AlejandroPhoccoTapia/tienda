from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("negocio", "0004_distribuir_comision_por_producto"),
    ]

    operations = [
        migrations.AddField(
            model_name="venta",
            name="cerrada",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="venta",
            name="fecha_cierre",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
