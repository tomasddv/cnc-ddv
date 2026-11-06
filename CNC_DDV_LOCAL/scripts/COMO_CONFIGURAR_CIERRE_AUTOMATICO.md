# DDV · Cierres automáticos desde Google Drive

## Fuentes verificadas en la carpeta "planificacion"

- Carpeta fuente: `1cukgXLUaPsEDK_yD7tSwgaBFZAbiDUot`.
- `ventadiaria octubre.txt` → cierre comercial octubre de 2026.
- `ventadiaria.txt` → ventas del mes **en curso**; **no** se toma como cierre.
- `venta septiembre.txt`, `venta agosto.txt` y archivos equivalentes: históricos.
- `reporte de clientes.xlsx`: padrón de **clientes activos**. En la revisión del 06/11/2026 su fecha de modificación era **26/10/2026**.
- El padrón completo de activos y anulados suministrado originalmente se mantiene en `clientes.csv.gz`.

## Proceso mensual

1. Termina noviembre. Se sube el archivo `ventadiaria noviembre.txt` (o `venta noviembre.txt`) con el mes completo.
2. Se actualiza/reemplaza `reporte de clientes.xlsx` con el padrón de activos de **cierre de noviembre**.
3. El proceso programado, desde diciembre, verifica que los dos estén actualizados después del cierre. Por precaución, el reporte de activos debe haberse actualizado durante los **primeros 15 días** del mes siguiente; de lo contrario, exige revisión manual, porque pudo haber sido reemplazado por un cierre posterior.
4. Lee `clientes.csv.gz` para el primer cierre y, para los siguientes, el **último snapshot cerrado**.
5. Si un cliente antes vigente ya no está en el nuevo padrón: **baja detectada en ese mes**, día no confirmado. NO se inventa una fecha de baja.
6. Guarda `clientes_cierre_2026-11.csv.gz`, `ventas_cierre_2026-11.csv.gz` y agrega noviembre a `ventas_resumen.csv.gz`, **reemplazando** cualquier noviembre parcial que hubiera allí.
7. Registra `2026-11` en `cierres_index.json`. El índice se actualiza AL FINAL; un cierre a medias no debe aparecer publicado.
8. En el dashboard, `2026-11` aparece en el selector. El administrador puede crear la campaña de promotores de ese cierre; las respuestas anteriores no se sobrescriben.

Si falta la venta nominada por mes o el reporte sigue con fecha anterior al cierre, el trabajo sale en estado `pendiente` y prueba de nuevo al día siguiente. El mes en curso jamás se publica como cierre.

## Requisitos antes de activar la programación

- Repositorio **privado** de GitHub con la carpeta `CNC_DDV_LOCAL/` en la raíz y `.github/workflows/cierre_cnc_ddv.yml`.
- Crear una cuenta de servicio de Google Cloud y compartirle con permiso **Lector** la carpeta fuente `planificacion` y con permiso **Editor** la carpeta destino privado `CNC privados`. No se modifican los archivos originales de la fuente.
- Secrets de GitHub Actions, en el repositorio: `GCP_SERVICE_ACCOUNT_JSON` (JSON de cuenta de servicio), `CNC_DRIVE_ORIGEN` (`1cukgXLUaPsEDK_yD7tSwgaBFZAbiDUot`) y `CNC_DRIVE_PRIVADOS` (`1_1Lhyr8axHXx4xy722mdBOXRY-oHe_DY`).
- La carpeta privada debe contener `clientes.csv.gz` y `ventas_resumen.csv.gz` con los IDs originales; el proceso modifica solo **el archivo de ventas consolidadas** en su ID actual y agrega snapshots nuevos. Nunca reemplaza el maestro histórico original.
- En Streamlit Cloud `CNC_DDV_LOCAL`, conservar `sales_snapshot_id` apuntando al `ventas_resumen.csv.gz` privado, `clients_snapshot_id` apuntando al maestro original, y agregar `private_data_folder_id` (`1_1Lhyr8axHXx4xy722mdBOXRY-oHe_DY`). El tablero descubrirá automáticamente `cierres_index.json` dentro de esa carpeta cuando aparezca el primer cierre; `cierres_index_id` es opcional.
- En los dos tableros usar la misma `DATABASE_URL` PostgreSQL para persistir respuestas de promotores. Sin PostgreSQL, la app de promotores local no guarda las respuestas de los 13 promotores en una base común.

## Inicio de cierre manual supervisado (alternativa)

```bash
python CNC_DDV_LOCAL/scripts/cerrar_mes_drive.py --origen 1cukgXLUaPsEDK_yD7tSwgaBFZAbiDUot --destino 1_1Lhyr8axHXx4xy722mdBOXRY-oHe_DY --credenciales cuenta-servicio.json --simular
```

El parámetro `--confirmar-reporte` permite procesar un reporte modificado el último día del mes, **solo después de revisar expresamente que corresponde al cierre**. No se usa en la programación automática.

## Advertencias comerciales

- Las fechas de anulación del padrón original tienen prioridad. Una baja inferida por ausencia conserva **solo el mes detectado**, sin inventar el día.
- La licencia CZA y el supervisor para los nuevos cierres son los del reporte actualizado. Los cierres anteriores permanecen archivados.
- El archivo `reporte de clientes.xlsx` de 26/10 no puede acreditar el cierre de octubre ni noviembre sin una actualización posterior.
- Mantener el archivo mensual de ventas con el mes en su **nombre**. No renombrar `ventadiaria.txt` de noviembre si ya contiene ventas de diciembre mezcladas.
