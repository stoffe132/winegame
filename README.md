# WineGame

Browser-based Wine64/Boxedwine launcher deployed with GitHub Pages.

The GitHub Actions workflow builds the WebAssembly version of Boxedwine64 and
packages the required root filesystem assets into the Pages deployment.

After the first successful deployment, the site is available at:

https://stoffe132.github.io/winegame/



## Graphics support

The browser launcher now exposes a graphics selector for:

- Auto
- OpenGL / WebGL2
- Direct3D / WineD3D
- Software
- Vulkan (fallback)
- DXVK (fallback)

The current BoxedWine64 browser backend has a real OpenGL→WebGL2 path and experimental Direct3D 9→WineD3D→WebGL2 path. The upstream browser build does not currently expose a Vulkan backend, so Vulkan/DXVK selections safely fall back instead of pretending they are active. Upstream BoxedWine's native/32-bit builds have broader Direct3D/OpenGL/Vulkan support, but that is not the same as browser support. citeturn0search0turn0search2

The Wine runtime supplies its open-source Wine DLLs. This project does not bundle proprietary Microsoft DLLs or Windows system files.
