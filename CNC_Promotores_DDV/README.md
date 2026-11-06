# CNC DDV · relevamiento simple para promotores

Aplicación independiente, diseñada para celulares: **un enlace único** para todos, una tarjeta por cliente, cuatro motivos tocables, avance automático y registro centralizado.

## Comportamiento

1. Ingreso: el promotor escribe su **nombre completo** o el **código de cualquiera de sus clientes asignados**, y su **código personal** cuando la app está publicada.
2. Ve **un cliente por vez**: nombre de fantasía, razón social, código y negocio(s) CNC.
3. Toca **💸 Sin dinero / 🚪 Cerrado / 🛒 Compra en súper o mayorista / ✍️ Otro**. Si elige Otro debe añadir un comentario breve.
4. La respuesta se guarda y aparece el siguiente cliente. Los completados salen de pendientes; hay una opción para revisar/corregir.
5. Un cliente CNC tanto en **CZA como UNG figura una sola vez**. **Una respuesta se guarda en los dos negocios**. El CSV de auditoría por negocio preserva esas dos filas para alimentar el tablero CNC.
6. El administrador consulta avance por promotor, pendientes, motivos y descarga CSV.

## Cartera inicial

La campaña demostrativa de **octubre 2026** fue generada desde el motor CNC de DDV. Solo incluye vigentes al cierre, promotor asignado, antigüedad U3M cumplida y, en CZA, licencia de alcohol SI:

- **357 casos cliente-negocio**: 132 CZA y 225 UNG.
- **268 clientes únicos**: 89 se repiten en ambos negocios, pero aparecen una vez.
- **13 promotores**.

Los datos son una **foto congelada**, no conectada en vivo a ventas. El administrador puede importar la cartera del próximo mes desde CSV validado sin eliminar respuestas históricas.

## Prueba local en Windows

1. Descomprimir el ZIP completo, no ejecutar desde adentro del archivo comprimido.
2. Tener Python 3.11+ instalado, con `py -3` o `python` en PATH, y conexión a Internet para instalar dependencias la primera vez.
3. Ejecutar `INICIAR_PROMOTORES_LOCAL.bat`.
4. Abrir `http://localhost:8520` (el iniciador espera a que Streamlit responda y abre el navegador).
5. Ingresar el **nombre completo** de un promotor o el **código de uno de sus clientes**. En modo local no se exige PIN. Para ver nombres disponibles usar `¿No recordás el nombre exacto?`.
6. La base persiste en `data/relevamientos.sqlite`. **Guardar ese archivo** antes de extraer versiones posteriores.
7. Para el control de pruebas, pulsar **Control de supervisión** en la pantalla inicial; solo se abre sin clave cuando el BAT activa `LOCAL_DEMO=1`.

### Enlace único para todos (publicación)

1. Crear un repositorio **privado** con el contenido del ZIP **CNC_Promotores_Codigo_Sin_Datos.zip**. No subir `data/campana_2026-10.csv`, `*.sqlite` ni credenciales a un repositorio público.
2. Crear una base **PostgreSQL persistente** (por ejemplo Neon), anotar la cadena `DATABASE_URL` con SSL. **SQLite local no debe usarse como base compartida en Streamlit Cloud**: reinicios o varias instancias pueden perder respuestas.
3. Publicar `app.py` en Streamlit Community Cloud, conectando el repo privado. En **Secrets**, establecer `DATABASE_URL` y `ADMIN_PASSWORD` (ver `.streamlit/secrets.toml.example`). **NO configurar `LOCAL_DEMO=1`** en la nube.
4. Abrir el enlace publicado como **administrador**. Con la contraseña, subir el CSV validado de campaña (se entrega como archivo **privado**, separado del repo). Con el control `Crear códigos para promotores que aún no tienen`, descargar las credenciales generadas y enviarlas individualmente a cada promotor.
5. **Enviar la misma URL base a todos** (ej.: `https://cnc-ddv-promotores.streamlit.app`). Cada promotor entra con nombre o código de cliente **más su PIN personal**. No hay enlaces individuales.
6. Para otros meses, subir un nuevo CSV de campaña desde el panel administrativo y revisar el total de clientes únicos antes de confirmarlo.

**Seguridad:** el nombre o el código de un cliente no es una contraseña y **no garantiza privacidad**. En nube la aplicación exige además un código personal generado por el administrador, almacena solo su hash, restringe las consultas por promotor y permite exportar todos los clientes únicamente desde control protegido por contraseña. No usar `LOCAL_DEMO=1` en un servidor accesible por Internet.

## Estructura

- `app.py`: interfaz Streamlit móvil.
- `store.py`: lógica, SQLite/PostgreSQL, importación y exportación, PIN y auditoría.
- `data/campana_2026-10.csv`: **solo paquete privado de prueba**, no subir a repositorios.
- `tests/test_app_logic.py`: pruebas de agrupación de CZA/UNG, acceso y avance.
- `.streamlit/config.toml`: tema visual.
- `INICIAR_PROMOTORES_LOCAL.bat`: instalador/lanzador Windows.
- `.streamlit/secrets.toml.example`: modelo de credenciales sin claves reales.

## Alcance y limitaciones

- **Una respuesta por cliente** aplicada a ambos negocios es una decisión operativa solicitada expresamente. Si las causas difieren por negocio, se deberá cambiar la modalidad a dos preguntas por cliente.
- El PIN personal protege el acceso publicado, pero el código de cliente por sí solo no autentica a nadie.
- Importar clientes de un nuevo mes es una acción del administrador; no hay sincronización automática del motor CNC con Drive/BEES Force todavía.
- El relevamiento de esta app es una **gestión operativa**, no equivale automáticamente a una tarea BEES Force validada por el sistema oficial de Quilmes.
- Las respuestas están en la base local SQLite durante pruebas y solo se vuelven compartidas en línea mediante PostgreSQL persistente.
