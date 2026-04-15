
// ── File open/edit ────────────────────────────────────────────
function ideOpenFile(name) {
    ideAutosave();
    IDE.activeFile = name;

    if (!IDE.openFiles.find(f => f === name)) {
        IDE.openFiles.push(name);
    }

    ideRenderTabs();
    ideRenderFileTree();

    const code = IDE.current.files[name] || '';
    const ta   = document.getElementById('ide-textarea');
    ta.value   = code;

    document.getElementById('ide-no-file').style.display   = 'none';
    document.getElementById('ide-code-wrap').style.display = 'flex';

    ideUpdateHighlight();
    ideUpdateGutter();
    ideLintCode(code);
    // Обновляем превью при смене файла
    if (name.endsWith('.arx') && IDE.previewVisible) {
        ideUpdatePreview(code, name);
    }
}

function ideAutosave() {
    if (!IDE.current || !IDE.activeFile) return;
    const ta = document.getElementById('ide-textarea');
    if (!ta) return;
    IDE.current.files[IDE.activeFile] = ta.value;
    const idx = IDE.projects.findIndex(p => p.id === IDE.current.id);
    if (idx >= 0) { IDE.projects[idx] = IDE.current; ideSave(); }
}

function ideOnInput() {
    // Пропускаем обновления во время IME composition (предотвращает дублирование слов)
    if (window._ideComposing) return;
    ideUpdateHighlight();
    ideUpdateGutter();
    const ta = document.getElementById('ide-textarea');
    ideLintCode(ta.value);
    ideSimRefresh();
    // Обновляем превью для .arx файлов
    if (IDE.activeFile && IDE.activeFile.endsWith('.arx')) {
        ideUpdatePreview(ta.value, IDE.activeFile);
    }
}

function ideToggleExplorer() {
    const sb  = document.getElementById('ide-sidebar');
    const btn = document.getElementById('ide-toggle-explorer');
    const hide = !sb.classList.toggle('ide-panel-hidden');
    btn.classList.toggle('active', hide);
}

function ideToggleConsole() {
    const con = document.getElementById('ide-console');
    const btn = document.getElementById('ide-toggle-console');
    const hide = !con.classList.toggle('ide-panel-hidden');
    btn.classList.toggle('active', hide);
}

function ideOnScroll() {
    const ta = document.getElementById('ide-textarea');
    const hl = document.getElementById('ide-highlight');
    const gt = document.getElementById('ide-gutter');
    if (hl) { hl.scrollTop = ta.scrollTop; hl.scrollLeft = ta.scrollLeft; }
    if (gt) gt.scrollTop = ta.scrollTop;
}

function ideOnKeydown(e) {
    if (e.key === 'Tab') {
        e.preventDefault();
        const ta  = document.getElementById('ide-textarea');
        const s   = ta.selectionStart, end = ta.selectionEnd;
        ta.value  = ta.value.substring(0, s) + '    ' + ta.value.substring(end);
        ta.selectionStart = ta.selectionEnd = s + 4;
        ideUpdateHighlight();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault(); ideAutosave();
        ideLog('output', '✓ Saved', 'ok');
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault(); ideRun();
    }
}

// ── Tabs ──────────────────────────────────────────────────────
function ideRenderTabs() {
    const bar = document.getElementById('ide-file-tabs');
    if (!bar) return;
    bar.innerHTML = '';
    IDE.openFiles.forEach(name => {
        const tab = document.createElement('div');
        tab.className = 'ide-tab' + (name === IDE.activeFile ? ' active' : '');
        tab.innerHTML = `<span>${_esc(name)}</span>
            <button onclick="event.stopPropagation();ideCloseTab('${_esc(name)}')">×</button>`;
        tab.onclick = () => ideOpenFile(name);
        bar.appendChild(tab);
    });
}

function ideCloseTab(name) {
    IDE.openFiles = IDE.openFiles.filter(f => f !== name);
    if (IDE.activeFile === name) {
        IDE.activeFile = IDE.openFiles[IDE.openFiles.length - 1] || null;
        if (IDE.activeFile) ideOpenFile(IDE.activeFile);
        else {
            document.getElementById('ide-no-file').style.display   = 'flex';
            document.getElementById('ide-code-wrap').style.display = 'none';
            ideRenderTabs();
        }
    } else { ideRenderTabs(); }
}

// ── New file / folder ─────────────────────────────────────────
function ideNewFile()   {
    IDE.newFileIsDir = false;
    _showNewFileModal('New File', 'filename.grav');
}
function ideNewFolder() { IDE.newFileIsDir = true;  _showNewFileModal('New Folder', 'folder_name'); }

function _showNewFileModal(title, ph) {
    document.getElementById('ide-newfile-title').textContent = title;
    document.getElementById('ide-newfile-name').value = '';
    document.getElementById('ide-newfile-name').placeholder = ph;
    document.getElementById('ide-newfile-overlay').style.display = 'flex';
    document.getElementById('ide-newfile-modal').classList.add('open');
    setTimeout(() => document.getElementById('ide-newfile-name').focus(), 80);
}
function ideHideNewFile() {
    document.getElementById('ide-newfile-overlay').style.display = 'none';
    document.getElementById('ide-newfile-modal').classList.remove('open');
}
function ideConfirmNewFile() {
    const name = document.getElementById('ide-newfile-name').value.trim();
    if (!name || !IDE.current) return;
    if (IDE.newFileIsDir) {
        if (!IDE.current.folders) IDE.current.folders = [];
        // subfolder: store as "parent/child"
        const parent = IDE._pendingParentFolder;
        IDE._pendingParentFolder = null;
        const folderName = parent ? parent + '/' + name : name;
        IDE.current.folders.push(folderName);
    } else {
        // Определяем расширение по выбранному радио (grav/arx)
        const langRadio = document.querySelector('input[name="ide-newfile-lang"]:checked');
        const selectedExt = langRadio?.value === 'arx' ? '.arx' : '.grav';
        const base   = name.includes('.') ? name : name + selectedExt;
        const parent = IDE.newFileParent;
        const fname  = parent ? parent + '/' + base : base;
        IDE.current.files[fname] = '// ' + base + '\n\n';
        IDE.newFileParent = null;
        if (parent) IDE.expandedFolders.add(parent);
        ideOpenFile(fname);
    }
    ideSave(); ideRenderFileTree(); ideHideNewFile();
}

function ideDeleteFile(name) {
    if (!confirm((typeof t==='function'?t('ide.deleteFileConfirm'):'Delete') + ` "${name}"?`)) return;
    delete IDE.current.files[name];
    IDE.openFiles = IDE.openFiles.filter(f => f !== name);
    if (IDE.activeFile === name) {
        IDE.activeFile = IDE.openFiles[0] || null;
        if (IDE.activeFile) ideOpenFile(IDE.activeFile);
        else { document.getElementById('ide-no-file').style.display='flex'; document.getElementById('ide-code-wrap').style.display='none'; }
    }
    ideSave(); ideRenderFileTree(); ideRenderTabs();
}
