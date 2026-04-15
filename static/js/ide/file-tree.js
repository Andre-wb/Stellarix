// ── File tree ─────────────────────────────────────────────────
function ideRenderFileTree() {
    const tree = document.getElementById('ide-file-tree');
    if (!tree || !IDE.current) return;
    tree.innerHTML = '';

    const folders = IDE.current.folders || [];
    const files   = IDE.current.files   || {};

    // Root-level folders (no '/' in name) and root-level files
    const rootFolders = folders.filter(f => !f.includes('/'));
    const rootFiles   = Object.keys(files).filter(n => !n.includes('/'));

    _renderFolderContents(tree, rootFolders, rootFiles, folders, files, 0);
}

function _renderFolderContents(container, subFolders, fileNames, allFolders, allFiles, depth) {
    const indent = depth * 14;

    subFolders.forEach(folder => {
        const expanded = IDE.expandedFolders.has(folder);
        const row = document.createElement('div');
        row.className = 'ide-tree-folder';
        row.style.paddingLeft = indent + 'px';
        row.innerHTML = `
            <svg class="ide-tree-arrow" width="10" height="10" fill="currentColor" viewBox="0 0 24 24"
                 style="transition:transform .15s;transform:rotate(${expanded ? 90 : 0}deg);flex-shrink:0;opacity:.5">
                <path d="M10 17l5-5-5-5v10z"/>
            </svg>
            <svg width="13" height="13" fill="#fbbf24" viewBox="0 0 24 24" style="flex-shrink:0">
                <path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/>
            </svg>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(folder.split('/').pop())}</span>
            <button class="ide-tree-ctx-btn" onclick="event.stopPropagation();ideFolderCtx('${_esc(folder)}',event)" title="Options">⋯</button>`;
        // double-click to expand/collapse
        row.ondblclick = () => {
            if (IDE.expandedFolders.has(folder)) IDE.expandedFolders.delete(folder);
            else IDE.expandedFolders.add(folder);
            ideRenderFileTree();
        };
        container.appendChild(row);

        if (expanded) {
            // Direct child files of this folder (exactly one level deep)
            const childFiles = Object.keys(allFiles)
                .filter(n => n.startsWith(folder + '/') && !n.slice(folder.length + 1).includes('/'));
            childFiles.forEach(name => {
                const short = name.slice(folder.length + 1);
                const item = document.createElement('div');
                item.className = 'ide-tree-file ide-tree-child' + (IDE.activeFile === name ? ' active' : '');
                item.dataset.name = name;
                item.style.paddingLeft = (indent + 14) + 'px';
                item.innerHTML = `
                    ${_fileIcon(short)}
                    <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(short)}</span>
                    <button class="ide-tree-del" onclick="event.stopPropagation();ideDeleteFile('${_esc(name)}')" title="Delete">×</button>`;
                item.onclick = () => ideOpenFile(name);
                container.appendChild(item);
            });

            // Direct child subfolders (path = folder/childName, no further slashes after)
            const childFolders = allFolders.filter(f =>
                f.startsWith(folder + '/') && !f.slice(folder.length + 1).includes('/')
            );
            _renderFolderContents(container, childFolders, [], allFolders, allFiles, depth + 1);
        }
    });

    // Root files (only at depth 0)
    if (depth === 0) {
        fileNames.forEach(name => {
            const item = document.createElement('div');
            item.className = 'ide-tree-file' + (IDE.activeFile === name ? ' active' : '');
            item.dataset.name = name;
            item.innerHTML = `
                ${_fileIcon(name)}
                <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(name)}</span>
                <button class="ide-tree-del" onclick="event.stopPropagation();ideDeleteFile('${_esc(name)}')" title="Delete">×</button>`;
            item.onclick = () => ideOpenFile(name);
            container.appendChild(item);
        });
    }
}

// ── File icon helper ───────────────────────────────────────────
function _fileIcon(name, size = 12) {
    if (name.endsWith('.grav')) {
        return `<img src="/logo/gravitix.svg" width="${size}" height="${size}" style="flex-shrink:0;opacity:.85" alt=".grav">`;
    }
    if (name.endsWith('.arx')) {
        return `<img src="/logo/architex.svg" width="${size}" height="${size}" style="flex-shrink:0;opacity:.85" alt=".arx">`;
    }
    return `<svg width="${size}" height="${size}" fill="var(--text3)" viewBox="0 0 24 24" style="flex-shrink:0"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>`;
}

// ── Folder context menu ────────────────────────────────────────
function ideFolderCtx(folder, e) {
    IDE.ctxFolder = folder;
    const menu = document.getElementById('ide-folder-menu');
    if (!menu) return;
    menu.style.display = 'block';
    // Position near click, stay inside viewport
    const x = Math.min(e.clientX, window.innerWidth  - 180);
    const y = Math.min(e.clientY, window.innerHeight - 220);
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';
    setTimeout(() => document.addEventListener('click', _closeFolderCtx, { once: true }), 0);
}
function _closeFolderCtx() {
    const menu = document.getElementById('ide-folder-menu');
    if (menu) menu.style.display = 'none';
    IDE.ctxFolder = null;
}

function ideFolderAddFile() {
    const folder = IDE.ctxFolder; _closeFolderCtx();
    if (!folder) return;
    IDE.newFileIsDir  = false;
    IDE.newFileParent = folder;
    const ext = IDE.current?.lang === 'architex' ? '.arx' : '.grav';
    _showNewFileModal('New File in ' + folder, 'filename' + ext);
}
function ideFolderAddFolder() {
    const folder = IDE.ctxFolder; _closeFolderCtx();
    if (!folder) return;
    IDE.newFileIsDir     = true;
    IDE.newFileParent    = folder;
    IDE._pendingParentFolder = folder;
    _showNewFileModal('New Subfolder in ' + folder.split('/').pop(), 'subfolder_name');
}
function ideFolderRename() {
    const folder = IDE.ctxFolder; _closeFolderCtx();
    if (!folder || !IDE.current) return;
    const newName = prompt((typeof t==='function'?t('ide.renameFolder'):'Rename folder:'), folder);
    if (!newName || newName === folder) return;
    // Rename folder in list
    const idx = IDE.current.folders.indexOf(folder);
    if (idx >= 0) IDE.current.folders[idx] = newName;
    // Rename all files inside it
    const newFiles = {};
    Object.entries(IDE.current.files).forEach(([k, v]) => {
        newFiles[k.startsWith(folder + '/') ? newName + '/' + k.slice(folder.length + 1) : k] = v;
    });
    IDE.current.files = newFiles;
    // Fix open tabs
    IDE.openFiles = IDE.openFiles.map(f => f.startsWith(folder + '/') ? newName + '/' + f.slice(folder.length + 1) : f);
    if (IDE.activeFile && IDE.activeFile.startsWith(folder + '/'))
        IDE.activeFile = newName + '/' + IDE.activeFile.slice(folder.length + 1);
    IDE.expandedFolders.delete(folder); IDE.expandedFolders.add(newName);
    ideSave(); ideRenderFileTree(); ideRenderTabs();
}
function ideFolderCopy() {
    const folder = IDE.ctxFolder; _closeFolderCtx();
    if (!folder || !IDE.current) return;
    let copyName = folder + '_copy';
    let i = 2;
    while (IDE.current.folders.includes(copyName)) copyName = folder + '_copy' + (i++);
    IDE.current.folders.push(copyName);
    Object.entries(IDE.current.files).forEach(([k, v]) => {
        if (k.startsWith(folder + '/')) IDE.current.files[copyName + '/' + k.slice(folder.length + 1)] = v;
    });
    ideSave(); ideRenderFileTree();
}
function ideFolderDelete() {
    const folder = IDE.ctxFolder; _closeFolderCtx();
    if (!folder || !IDE.current) return;
    if (!confirm((typeof t==='function'?t('ide.deleteFolderConfirm'):'Delete folder') + ` "${folder}"?`)) return;
    IDE.current.folders = IDE.current.folders.filter(f => f !== folder);
    Object.keys(IDE.current.files).forEach(k => {
        if (k.startsWith(folder + '/')) delete IDE.current.files[k];
    });
    IDE.openFiles  = IDE.openFiles.filter(f => !f.startsWith(folder + '/'));
    if (IDE.activeFile && IDE.activeFile.startsWith(folder + '/')) {
        IDE.activeFile = IDE.openFiles[0] || null;
        if (IDE.activeFile) ideOpenFile(IDE.activeFile);
        else { document.getElementById('ide-no-file').style.display='flex'; document.getElementById('ide-code-wrap').style.display='none'; }
    }
    IDE.expandedFolders.delete(folder);
    ideSave(); ideRenderFileTree(); ideRenderTabs();
}
