# Control de tienda

Aplicación local en Django para consultar productos, pedidos y ventas.

## Puesta en marcha (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py cargar_demo
.\.venv\Scripts\python.exe manage.py runserver
```

Abre `http://127.0.0.1:8000/`.

Los datos de prueba se pueden volver a cargar sin duplicar catálogos ni pedidos.
