const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow;
let pythonProcess = null;
const SERVER_URL = 'http://127.0.0.1:5241';

function checkServerReady(cb) {
  http.get(`${SERVER_URL}/api/status`, (res) => {
    if (res.statusCode === 200) cb(true);
    else setTimeout(() => checkServerReady(cb), 200);
  }).on('error', () => {
    setTimeout(() => checkServerReady(cb), 200);
  });
}

function startPythonBackend() {
  const pythonPath = process.platform === 'win32' ? 'python' : 'python3';
  const serverScript = path.join(__dirname, '..', 'backend', 'server.py');
  pythonProcess = spawn(pythonPath, [serverScript], {
    cwd: path.join(__dirname, '..')
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python]: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python Err]: ${data}`);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 620,
    backgroundColor: '#0a0e17',
    show: false,
    titleBarStyle: 'default',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  checkServerReady(() => {
    mainWindow.loadURL(SERVER_URL);
    mainWindow.once('ready-to-show', () => {
      mainWindow.show();
    });
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  startPythonBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
