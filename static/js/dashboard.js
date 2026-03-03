/**
 * Dashboard UI Controller
 * Handles device list, modals, and API interactions
 */

let topology3d;
let selectedDevice = null;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize 3D topology
    topology3d = new Topology3D('canvas-container');
    
    // Load initial data
    loadData();
    
    // Set up event listeners
    setupEventListeners();
    
    // Auto-refresh every 30 seconds
    setInterval(loadData, 30000);
});

function setupEventListeners() {
    // Reset view button
    document.getElementById('resetView').addEventListener('click', () => {
        topology3d.resetView();
    });
    
    // Refresh data button
    document.getElementById('refreshData').addEventListener('click', () => {
        loadData();
        showToast('Data refreshed', 'success');
    });
    
    // Modal close button
    document.querySelector('.close').addEventListener('click', () => {
        closeModal();
    });
    
    // Close modal when clicking outside
    window.addEventListener('click', (event) => {
        const modal = document.getElementById('deviceModal');
        if (event.target === modal) {
            closeModal();
        }
    });
    
    // Modal action buttons
    document.getElementById('locateBtn').addEventListener('click', () => {
        if (selectedDevice) {
            locateDevice(selectedDevice.id);
        }
    });
    
    document.getElementById('requestImageBtn').addEventListener('click', () => {
        if (selectedDevice) {
            requestImage(selectedDevice.id);
        }
    });
    
    document.getElementById('viewImageBtn').addEventListener('click', () => {
        if (selectedDevice) {
            window.location.href = `/view-image/${selectedDevice.id}`;
        }
    });
}

async function loadData() {
    try {
        // Load stationary nodes
        const nodesResponse = await fetch('/api/stationary-nodes');
        const nodesData = await nodesResponse.json();
        
        if (nodesData.success) {
            nodesData.nodes.forEach(node => {
                if (!topology3d.nodeMeshes.has(node.id)) {
                    topology3d.addStationaryNode(node);
                }
            });
        }
        
        // Load devices
        const devicesResponse = await fetch('/api/devices');
        const devicesData = await devicesResponse.json();
        
        if (devicesData.success) {
            topology3d.updateDevices(devicesData.devices);
            updateDeviceList(devicesData.devices);
        }
    } catch (error) {
        console.error('Error loading data:', error);
        showToast('Failed to load data', 'error');
    }
}

function updateDeviceList(devices) {
    const deviceList = document.getElementById('deviceList');
    const deviceCount = document.getElementById('deviceCount');
    
    deviceCount.textContent = devices.length;
    deviceList.innerHTML = '';
    
    devices.forEach(device => {
        const deviceCard = createDeviceCard(device);
        deviceList.appendChild(deviceCard);
    });
}

function createDeviceCard(device) {
    const card = document.createElement('div');
    card.className = 'device-card';
    card.onclick = () => showDeviceDetails(device);
    
    const statusClass = getStatusClass(device.status);
    const batteryIcon = getBatteryIcon(device.battery_level);
    
    card.innerHTML = `
        <div class="device-header">
            <h3>${device.patient_name}</h3>
            <span class="badge badge-${statusClass}">${device.status}</span>
        </div>
        <div class="device-info">
            <div class="info-row">
                <span class="label">Device ID:</span>
                <span class="value">${device.id}</span>
            </div>
            <div class="info-row">
                <span class="label">Room:</span>
                <span class="value">${device.room}</span>
            </div>
            <div class="info-row">
                <span class="label">Battery:</span>
                <span class="value">${batteryIcon} ${device.battery_level}%</span>
            </div>
            <div class="info-row">
                <span class="label">Heart Rate:</span>
                <span class="value">${device.heart_rate} bpm</span>
            </div>
            <div class="info-row">
                <span class="label">Temperature:</span>
                <span class="value">${device.temperature}°C</span>
            </div>
            <div class="info-row">
                <span class="label">Location:</span>
                <span class="value">X:${device.location.x.toFixed(1)}m Y:${device.location.y.toFixed(1)}m</span>
            </div>
        </div>
    `;
    
    return card;
}

function showDeviceDetails(device) {
    selectedDevice = device;
    
    const modal = document.getElementById('deviceModal');
    const modalTitle = document.getElementById('modalTitle');
    const modalBody = document.getElementById('modalBody');
    const viewImageBtn = document.getElementById('viewImageBtn');
    
    modalTitle.textContent = `${device.patient_name} - ${device.id}`;
    
    // Build detailed info
    modalBody.innerHTML = `
        <div class="detail-grid">
            <div class="detail-section">
                <h3>Patient Information</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>Name:</strong></td>
                        <td>${device.patient_name}</td>
                    </tr>
                    <tr>
                        <td><strong>Room:</strong></td>
                        <td>${device.room}</td>
                    </tr>
                    <tr>
                        <td><strong>Device ID:</strong></td>
                        <td>${device.id}</td>
                    </tr>
                </table>
            </div>
            
            <div class="detail-section">
                <h3>Device Status</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>Status:</strong></td>
                        <td><span class="badge badge-${getStatusClass(device.status)}">${device.status}</span></td>
                    </tr>
                    <tr>
                        <td><strong>Battery:</strong></td>
                        <td>${getBatteryIcon(device.battery_level)} ${device.battery_level}%</td>
                    </tr>
                    <tr>
                        <td><strong>Last Uplink:</strong></td>
                        <td>${formatTimestamp(device.last_uplink)}</td>
                    </tr>
                    <tr>
                        <td><strong>Wi-Fi Capable:</strong></td>
                        <td>${device.wifi_capable ? 'Yes' : 'No'}</td>
                    </tr>
                </table>
            </div>
            
            <div class="detail-section">
                <h3>Health Metrics</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>Heart Rate:</strong></td>
                        <td>${device.heart_rate} bpm</td>
                    </tr>
                    <tr>
                        <td><strong>Temperature:</strong></td>
                        <td>${device.temperature}°C</td>
                    </tr>
                </table>
            </div>
            
            <div class="detail-section">
                <h3>Location (RSSI-based)</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>X Coordinate:</strong></td>
                        <td>${device.location.x.toFixed(2)} m</td>
                    </tr>
                    <tr>
                        <td><strong>Y Coordinate:</strong></td>
                        <td>${device.location.y.toFixed(2)} m</td>
                    </tr>
                    <tr>
                        <td><strong>Z Coordinate:</strong></td>
                        <td>${device.location.z.toFixed(2)} m</td>
                    </tr>
                </table>
            </div>
            
            <div class="detail-section full-width">
                <h3>RSSI Readings</h3>
                <table class="detail-table">
                    ${Object.entries(device.rssi_readings).map(([node, rssi]) => `
                        <tr>
                            <td><strong>${node.toUpperCase()}:</strong></td>
                            <td>${rssi} dBm ${getRSSIStrength(rssi)}</td>
                        </tr>
                    `).join('')}
                </table>
            </div>
        </div>
    `;
    
    // Show/hide view image button based on availability
    viewImageBtn.style.display = device.has_image ? 'inline-block' : 'none';
    
    modal.style.display = 'block';
}

function closeModal() {
    const modal = document.getElementById('deviceModal');
    modal.style.display = 'none';
    selectedDevice = null;
}

async function locateDevice(deviceId) {
    try {
        showToast('Initiating location request...', 'info');
        
        const response = await fetch(`/api/locate/${deviceId}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            showToast(`Location request sent for device ${deviceId}. Waiting for uplink...`, 'success');
            
            // Refresh data after a few seconds
            setTimeout(() => {
                loadData();
            }, 3000);
        } else {
            showToast('Failed to locate device: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error locating device:', error);
        showToast('Error locating device', 'error');
    }
}

async function requestImage(deviceId) {
    try {
        showToast('Requesting image capture...', 'info');
        
        const response = await fetch(`/api/request-image/${deviceId}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            showToast(`Image request sent! Relay path: ${data.relay_path.join(' → ')}. ETA: ${data.estimated_time}`, 'success', 5000);
            
            // Update view image button after estimated time
            setTimeout(() => {
                loadData();
                closeModal();
            }, 5000);
        } else {
            showToast('Failed to request image: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error requesting image:', error);
        showToast('Error requesting image', 'error');
    }
}

// Helper functions
function getStatusClass(status) {
    const statusMap = {
        'active': 'success',
        'low_battery': 'warning',
        'offline': 'danger',
        'inactive': 'secondary'
    };
    return statusMap[status] || 'secondary';
}

function getBatteryIcon(level) {
    if (level > 75) return '';
    if (level > 50) return '';
    if (level > 25) return '⚠ ';
    return '⚠⚠ ';
}

function getRSSIStrength(rssi) {
    if (rssi > -50) return '(Excellent)';
    if (rssi > -60) return '(Good)';
    if (rssi > -70) return '(Fair)';
    if (rssi > -80) return '(Weak)';
    return '(Very Weak)';
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000); // seconds
    
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleString();
}

function showToast(message, type = 'info', duration = 3000) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast toast-${type} show`;
    
    setTimeout(() => {
        toast.className = 'toast';
    }, duration);
}
