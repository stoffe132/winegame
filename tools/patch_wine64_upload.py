#!/usr/bin/env python3
from pathlib import Path

root = Path("boxedwine64/project/emscripten")
html = root / "wine64.html"
js = root / "wine64-launcher.js"

s = html.read_text()
old = '''<input type="file" id="exeUpload" accept=".exe,application/x-msdownload,application/octet-stream" style="display:none"
             onchange="if (this.files[0] && window.uploadAndRunExe) { window.uploadAndRunExe(this.files[0]); this.value=''; }">
      <button type="button" onclick="document.getElementById('exeUpload').click()">⬆ Run my own .exe</button>
      <span class="tbhint">runs a Windows .exe you choose — best with a single <b>portable</b> Win32 app (not installers, .NET, or D3D games)</span>'''
new = '''<input type="file" id="exeUpload" accept=".exe,.zip,application/x-msdownload,application/zip,application/octet-stream" style="display:none"
             onchange="if (this.files[0] && window.uploadGameFile) { window.uploadGameFile(this.files[0]); this.value=''; }">
      <input type="file" id="folderUpload" webkitdirectory directory multiple style="display:none"
             onchange="if (this.files.length && window.uploadGameFolder) { window.uploadGameFolder(this.files); this.value=''; }">
      <button type="button" onclick="document.getElementById('exeUpload').click()">⬆ Upload game (.exe / .zip)</button>
      <button type="button" onclick="document.getElementById('folderUpload').click()">📁 Upload game folder</button>
      <span class="tbhint">upload an .exe, a ZIP, or a whole game folder. If it contains an .exe, WineGame finds it and launches it.</span>'''
if old not in s:
    raise SystemExit("expected upload HTML not found")
html.write_text(s.replace(old, new))

# Replace the single-file uploader with a general game importer.
src = js.read_text()
start = src.index("    // --- upload-your-own .exe")
end = src.index("    // --- orchestration", start)

replacement = r'''    // --- upload a Windows game (.exe, .zip, or folder) --------------------
    // Files supplied by the user stay in the browser sandbox; they are never
    // committed to GitHub.  ZIP support handles STORE and DEFLATE entries.
    function bw64FsReady() {
        return whenFsReady();
    }

    function bw64WriteGuestFile(rel, bytes) {
        var clean = rel.replace(/\\/g, "/").replace(/^/+/, "");
        if (!clean || clean.endsWith("/")) return;
        var parts = clean.split("/").filter(Boolean);
        var path = HOME_IN_MEMFS;
        for (var i = 0; i < parts.length - 1; i++) {
            path += "/" + parts[i];
            try { getFS().mkdir(path); } catch (e) {}
        }
        var dest = path + "/" + parts[parts.length - 1];
        try { getFS().unlink(dest); } catch (e) {}
        getFS().writeFile(dest, bytes);
        return "/home/username/" + clean;
    }

    function bw64Register(paths) {
        paths.forEach(function (p) {
            callExport("bw64_register_file", ["string"], [p]);
        });
    }

    function bw64PickExe(exes) {
        exes = exes.filter(function (x) { return /.exe$/i.test(x); });
        if (!exes.length) {
            alert("No .exe file was found in the selected game.");
            return null;
        }
        if (exes.length === 1) return exes[0];
        var message = "Several .exe files were found. Enter the number to launch:\n\n" +
            exes.map(function (x, i) { return (i + 1) + ". " + x; }).join("\n");
        var answer = prompt(message, "1");
        var n = Number(answer);
        return Number.isInteger(n) && n >= 1 && n <= exes.length ? exes[n - 1] : null;
    }

    function bw64LaunchGuestExe(guestPath) {
        var winPath = "Z:\\" + guestPath.replace(/^/+/, "").replace(///g, "\\");
        if (window.launchApp) window.launchApp(winPath);
        else window.location.search = "?p=" + encodeURIComponent(winPath);
    }

    function bw64ImportFiles(files) {
        if (!files || !files.length) return;
        if (!window.Module && !liveModule) {
            alert("Wine is still starting. Wait for the emulator to finish booting, then upload the game.");
            return;
        }
        bw64FsReady().then(function () {
            var list = Array.prototype.slice.call(files);
            var exes = [];
            var writes = [];
            list.forEach(function (file) {
                var rel = file.webkitRelativePath || file.name;
                // A plain .exe is placed at the root; folder uploads preserve
                // their relative game directory.
                rel = rel.replace(/^[^/]+/(?=[^/]+/)/, "");
                if (/.exe$/i.test(rel)) exes.push(rel);
                writes.push(new Promise(function (resolve, reject) {
                    var reader = new FileReader();
                    reader.onerror = function () { reject(new Error("Could not read " + file.name)); };
                    reader.onload = function () {
                        try {
                            var guest = bw64WriteGuestFile(rel, new Uint8Array(reader.result));
                            if (guest && /.exe$/i.test(rel)) exes.push(guest.replace(/^/home/username//, ""));
                            resolve();
                        } catch (e) { reject(e); }
                    };
                    reader.readAsArrayBuffer(file);
                }));
            });
            // Avoid duplicate EXE entries from the pre-read list.
            exes = [];
            return Promise.all(writes).then(function () {
                // Find EXEs by walking the selected paths again. For folder
                // uploads the paths are relative; for a direct EXE it is its name.
                list.forEach(function (f) {
                    var rel = f.webkitRelativePath || f.name;
                    rel = rel.replace(/^[^/]+/(?=[^/]+/)/, "");
                    if (/.exe$/i.test(rel)) exes.push(rel);
                });
                var picked = bw64PickExe(exes);
                if (!picked) return;
                var guest = "/home/username/" + picked.replace(/^/+/, "");
                callExport("bw64_register_file", ["string"], [guest]);
                // Register every file so sibling DLLs/data files are visible.
                var all = [];
                list.forEach(function (f) {
                    var rel = f.webkitRelativePath || f.name;
                    rel = rel.replace(/^[^/]+/(?=[^/]+/)/, "");
                    all.push("/home/username/" + rel.replace(/^/+/, ""));
                });
                bw64Register(all);
                bw64LaunchGuestExe(guest);
            });
        }).catch(function (e) {
            console.error(e);
            alert("Could not import the game: " + e);
        });
    }

    // Minimal ZIP reader: central directory + STORE/DEFLATE entries. This avoids
    // a third-party CDN dependency, which is important under COEP.
    function bw64ReadZip(file) {
        return file.arrayBuffer().then(function (ab) {
            var b = new Uint8Array(ab), dv = new DataView(ab), len = b.length;
            var pos = Math.max(0, len - 22), eocd = -1;
            for (var i = len - 22; i >= pos; i--) {
                if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
            }
            if (eocd < 0) throw new Error("Invalid ZIP: end-of-directory not found");
            var count = dv.getUint16(eocd + 10, true);
            var cdSize = dv.getUint32(eocd + 12, true);
            var cdOff = dv.getUint32(eocd + 16, true);
            if (cdOff + cdSize > len) throw new Error("Invalid ZIP directory");
            var entries = [];
            var p = cdOff;
            for (var n = 0; n < count; n++) {
                if (dv.getUint32(p, true) !== 0x02014b50) throw new Error("Invalid ZIP entry");
                var method = dv.getUint16(p + 10, true);
                var compSize = dv.getUint32(p + 20, true);
                var nameLen = dv.getUint16(p + 28, true);
                var extraLen = dv.getUint16(p + 30, true);
                var commentLen = dv.getUint16(p + 32, true);
                var localOff = dv.getUint32(p + 42, true);
                var nameBytes = b.subarray(p + 46, p + 46 + nameLen);
                var name = new TextDecoder("utf-8").decode(nameBytes);
                p += 46 + nameLen + extraLen + commentLen;
                if (!name || name.endsWith("/")) continue;
                entries.push({name:name, method:method, size:compSize, off:localOff});
            }
            return Promise.all(entries.map(function (e) {
                var lp = e.off;
                if (dv.getUint32(lp, true) !== 0x04034b50) throw new Error("Invalid ZIP local header");
                var nl = dv.getUint16(lp + 26, true), xl = dv.getUint16(lp + 28, true);
                var comp = b.slice(lp + 30 + nl + xl, lp + 30 + nl + xl + e.size);
                if (e.method === 0) return Promise.resolve({name:e.name, bytes:comp});
                if (e.method !== 8) throw new Error("ZIP compression method " + e.method + " is not supported");
                var stream = new Blob([comp]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
                return new Response(stream).arrayBuffer().then(function (raw) {
                    return {name:e.name, bytes:new Uint8Array(raw)};
                });
            }));
        });
    }

    function uploadGameFile(file) {
        if (/.zip$/i.test(file.name)) {
            bw64ReadZip(file).then(function (entries) {
                var exes = entries.filter(function (e) { return /.exe$/i.test(e.name); });
                if (!exes.length) { alert("The ZIP does not contain an .exe file."); return; }
                return bw64FsReady().then(function () {
                    var all = [];
                    entries.forEach(function (e) {
                        var name = e.name.replace(/^/+/, "");
                        if (!name || name.endsWith("/")) return;
                        var guest = bw64WriteGuestFile(name, e.bytes);
                        all.push(guest);
                    });
                    bw64Register(all);
                    var picked = bw64PickExe(exes.map(function (e) { return e.name; }));
                    if (picked) bw64LaunchGuestExe("/home/username/" + picked.replace(/^/+/, ""));
                });
            }).catch(function (e) {
                console.error(e); alert("Could not read the ZIP: " + e);
            });
        } else {
            bw64ImportFiles([file]);
        }
    }

    function uploadGameFolder(files) {
        bw64ImportFiles(files);
    }

    window.uploadGameFile = uploadGameFile;
    window.uploadGameFolder = uploadGameFolder;
    window.uploadAndRunExe = uploadGameFile;

'''
js.write_text(src[:start] + replacement + src[end:])
