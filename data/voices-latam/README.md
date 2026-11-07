# Voces en español latinoamericano — piloto

Base del fork: GCompris **V26.2**, la versión instalada en la Fire 7.
El resto del código y las licencias de KDE se mantienen.

## Primer lote

- `es/misc/welcome.ogg`: bienvenida nueva.
- `es/intro/enumerate.ogg`: contar elementos (añadido; faltaba en el paquete español).
- `es/intro/algebra_plus.ogg`: sumar.
- `es/intro/algebra_minus.ogg`: restar.

Las instrucciones proceden del catálogo español de la versión 26.2. La bienvenida
es una frase nueva. Los cuatro clips usan como referencia la muestra de voz
aprobada: narradora cálida, expresiva, español latinoamericano con seseo.

El manifiesto registra texto, destino, duración y trabajo de generación. La voz
aprobada como referencia no equivale a haber aprobado auditivamente cada clip.
Falta revisar las cuatro locuciones y comprobar su reproducción en la tableta.

## Empaquetado y comprobación

Desde la raíz:

```sh
python3 tools/latam/pack.py
```

Se descarga el paquete original desde KDE, se comprueba su MD5 contra el catálogo
y se extrae con Qt. El paquete nuevo añade la introducción de contar que faltaba,
mantiene todas las rutas anteriores y conserva los demás audios
byte por byte. Después se vuelve a extraer y comparar. Los originales y los
artefactos viven en directorios ignorados por Git; no se publican claves, datos
del perfil ni progreso de la tableta.

El resultado está en `tools/latam/build/`, junto a `Contents` y
`verification.json`. Conservar el nombre original permite que GCompris encuentre
el paquete, pero no garantiza que una descarga posterior de KDE no lo sustituya.
No activar actualizaciones de voces durante la prueba.

## Piloto Android instalado

La app de F-Droid no permite modificar sus datos privados mediante `run-as`.
No desinstalarla para cambiar la firma: eso podría borrar el progreso.
Se ha preparado una variante independiente, `net.gcompris.latn`, instalada solo
en el perfil 10. El acceso directo se llama **GCompris Latino**. La original,
`net.gcompris.full`, conserva sus datos y permanece instalada. La variante tiene
progreso propio; no se ha migrado el historial ni se ha borrado el original.

```sh
python3 tools/latam/android_pilot.py /ruta/al/APK-original-26.2-arm64.apk
adb -s SERIAL install --user 10 -r -t tools/latam/build/gcompris-latino.apk
```

Este piloto **no** es una compilación completa desde código fuente: reutiliza el
binario 26.2 de F-Droid y añade el paquete de audio en
`assets/data3/voices-ogg/`. Cambia el identificador Android y la etiqueta visible,
y se firma con la clave local de pruebas. El guion está incluido para que estos
cambios sean reproducibles. El código ejecutable original no se modifica.

Verificación en Fire 7: arranque correcto y registro del recurso nuevo en el log
de Qt (`Successfully registered resource assets:/data3/voices-ogg/...`). Las
descargas automáticas están desactivadas en la configuración. La ruta `es`
conserva la compatibilidad: la interfaz puede decir «español de España», pero
las cuatro locuciones de este lote son latinoamericanas. Los otros 899 audios
siguen siendo los originales. Falta la escucha final del dueño en el altavoz.

Los audios originales conservan sus licencias; los textos traducidos mantienen
sus avisos en `po/es/gcompris_voices.po`. No se modifica la licencia global del
proyecto ni se presupone una licencia nueva para los recursos de terceros.
