MONITOR AGUA DEMO V2

CAMBIOS
- Sin menú lateral.
- Una sola vista real: Resumen.
- PUL 1 reúne agua + temperatura + humedad.
- Los uplinks parciales se fusionan usando el último valor no nulo.
- Todos los textos visibles usan identificadores TEXTO_ fáciles de buscar.
- HTML comentado.
- Carpeta static/ para imágenes.

ARCHIVOS A EDITAR
1) templates/index.html
   Busca TEXTO_ con Ctrl+F.
2) templates/login.html
   Busca TEXTO_LOGIN_ con Ctrl+F.
3) static/
   Copia logos y fotografías aquí.
4) app.py
   No necesitas editarlo para cambiar textos.

RENDER
Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app

Variables:
DEMO_USER
DEMO_PASSWORD
SECRET_KEY

PARA ACTUALIZAR TU RENDER ACTUAL
- Reemplaza en GitHub los archivos por los de esta V2.
- Haz Commit.
- Render normalmente despliega automáticamente.
- Si no: Manual Deploy > Deploy latest commit.
