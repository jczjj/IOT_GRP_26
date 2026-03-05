/**
 * Dashboard UI Controller
 * Handles device list, modals, and API interactions
 * Auto-updates with real calculated positions from RSSI trilateration
 */

let topology3d;
let selectedDevice = null;
let dataRefreshInterval = null;
let autoLocalizeInterval = null;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize 3D topology
    topology3d = new Topology3D('canvas-container');
    
    // Load initial data
    loadData();
    
    // Set up event listeners
    setupEventListeners();
    
    // Auto-refresh data every 15 seconds
    dataRefreshInterval = setInterval(loadData, 15000);
    
    // Auto-trigger localization for devices with RSSI data every 30 seconds
    autoLocalizeInterval = setInterval(autoLocalizeDevices, 30000);
});

function setupEventListeners() {
    // Reset view button
    document.getElementById('resetView').addEventListener('click', () => {
        topology3d.resetView();
    });
    
    // Refresh data button
    document.getElementById('refreshData').addEventListener('click', () => {
        loadData();
        showToast('Fetching real-time positions...', 'info');
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
            triggerLocalization(selectedDevice.id);
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
        // Load stationary nodes (anchors)
        const nodesResponse = await fetch('/api/stationary-nodes');
        const nodesData = await nodesResponse.json();
        
        if (nodesData.success) {
            nodesData.nodes.forEach(node => {
                if (!topology3d.nodeMeshes.has(node.id)) {
                    topology3d.addStationaryNode(node);
                }
            });
        }
        
        // Load devices with real positions
        const devicesResponse = await fetch('/api/devices');
        const devicesData = await devicesResponse.json();
        
        if (devicesData.success) {
            // Update 3D visualization with real positions
            topology3d.updateDevices(devicesData.devices);
            
            // Update device list with position quality metrics
            updateDeviceList(devicesData.devices);
            
            // Trigger automatic localization for devices with RSSI data
            devicesData.devices.forEach(device => {
                if (device.rssi_readings && Object.keys(device.rssi_readings).length >= 3) {
                    // Device has RSSI readings from ≥3 nodes, ready for localization
                    localizeDeviceIfReady(device.id);
                }
            });
        }
    } catch (error) {
        console.error('Error loading data:', error);
        showToast('Failed to load data', 'error');
    }
}

async function autoLocalizeDevices() {
    try {
        const devicesResponse = await fetch('/api/devices');
        const devicesData = await devicesResponse.json();
        
        if (devicesData.success) {
            // Attempt to localize devices with sufficient RSSI data
            let localizationAttempted = false;
            
            devicesData.devices.forEach(device => {
                if (device.rssi_readings && Object.keys(device.rssi_readings).length >= 3) {
                    localizeDeviceIfReady(device.id);
                    localizationAttempted = true;
                }
            });
            
            if (localizationAttempted) {
                // Refresh after a short delay to show updated positions
                setTimeout(() => loadData(), 2000);
            }
        }
    } catch (error) {
        console.error('Error in auto-localization:', error);
    }
}

async function localizeDeviceIfReady(deviceId) {
    try {
        // Attempt trilateration with current RSSI data
        const response = await fetch(`/api/localize/${deviceId}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            console.log(`✓ Auto-localized ${deviceId}: (${data.position.x.toFixed(2)}, ${data.position.y.toFixed(2)}, ${data.position.z.toFixed(2)})m`);
            
            // Refresh device list to show updated position
            loadData();
            
            // If modal is open and showing this device, update it
            if (selectedDevice && selectedDevice.id === deviceId) {
                showDeviceDetails(selectedDevice);
            }
        }
    } catch (error) {
        console.error(`Error auto-localizing ${deviceId}:`, error);
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
    
    // Calculate RSSI measurement count
    const rssiCount = device.rssi_readings ? Object.keys(device.rssi_readings).length : 0;
    const localizationReady = rssiCount >= 3;
    const readyIndicator = localizationReady ? '✓ Ready' : `${rssiCount}/3`;
    const readyClass = localizationReady ? 'badge-success' : 'badge-warning';
    
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
                <span class="value">${device.heart_rate || '—'} bpm</span>
            </div>
            <div class="info-row">
                <span class="label">Temperature:</span>
                <span class="value">${device.temperature || '—'}°C</span>
            </div>
            <div class="info-row">
                <span class="label">Position (X,Y,Z):</span>
                <span class="value" style="font-family: monospace; font-size: 0.9em;">
                    ${device.location.x.toFixed(1)}m, ${device.location.y.toFixed(1)}m, ${device.location.z.toFixed(1)}m
                </span>
            </div>
            <div class="info-row">
                <span class="label">Localization:</span>
                <span class="value badge ${readyClass}">${readyIndicator}</span>
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
    
    // Calculate RSSI metrics
    const rssiReadings = device.rssi_readings || {};
    const rssiCount = Object.keys(rssiReadings).length;
    const localizationReady = rssiCount >= 3;
    
    // Build detailed info with localization data
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
                        <td><code>${device.id}</code></td>
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
                        <td>${device.wifi_capable ? '✓ Yes' : '✗ No'}</td>
                    </tr>
                </table>
            </div>
            
            <div class="detail-section">
                <h3>Health Metrics</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>Heart Rate:</strong></td>
                        <td>${device.heart_rate || '—'} bpm</td>
                    </tr>
                    <tr>
                        <td><strong>Temperature:</strong></td>
                        <td>${device.temperature || '—'}°C</td>
                    </tr>
                </table>
            </div>
            
            <div class="detail-section">
                <h3>📍 Calculated Position (RSSI-Based)</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>X Coordinate:</strong></td>
                        <td><code>${device.location.x.toFixed(3)}</code> m</td>
                    </tr>
                    <tr>
                        <td><strong>Y Coordinate:</strong></td>
                        <td><code>${device.location.y.toFixed(3)}</code> m</td>
                    </tr>
                    <tr>
                        <td><strong>Z Coordinate (Height):</strong></td>
                        <td><code>${device.location.z.toFixed(3)}</code> m</td>
                    </tr>
                    <tr>
                        <td><strong>Measurements Available:</strong></td>
                        <td>
                            <span class="badge ${localizationReady ? 'badge-success' : 'badge-warning'}">
                                ${rssiCount}/4 anchors
                            </span>
                            ${localizationReady ? ' ✓ Ready for localization' : ' Need more data'}
                        </td>
                    </tr>
                </table>
            </div>
            
            <div class="detail-section full-width">
                <h3>📡 RSSI Readings from Anchors</h3>
                <table class="detail-table">
                    ${Object.entries(rssiReadings).map(([node, rssi]) => {
                        const distance = estimateDistance(rssi);
                        return `
                        <tr>
                            <td><strong>${node.toUpperCase()}:</strong></td>
                            <td>
                                <code>${rssi}</code> dBm 
                                <span style="color: #999; font-size: 0.9em;">
                                    (${getRSSIStrength(rssi)} ~ ${distance.toFixed(1)}m)
                                </span>
                            </td>
                        </tr>
                    `;
                    }).join('')}
                </table>
                ${rssiCount === 0 ? '<p style="color: #ff9800; padding: 10px;">No RSSI data yet. Trigger location request to collect RSSI readings.</p>' : ''}
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

async function triggerLocalization(deviceId) {
    try {
        showToast('Sending location request to device...', 'info');
        
        // Send command to device to broadcast RSSI ping
        const response = await fetch(`/api/locate/${deviceId}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            showToast(`Location beacon sent! Collecting RSSI data... (waiting ${data.collect_timeout || 30}s)`, 'success');
            
            // Refresh data after collection period to trigger auto-localization
            setTimeout(() => {
                showToast('Calculating position from RSSI data...', 'info');
                loadData();
            }, (data.collect_timeout || 30) * 1000);
        } else {
            showToast('Failed to send location request: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error triggering localization:', error);
        showToast('Error sending location request', 'error');
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
        'inactive': 'secondary',
        'unknown': 'secondary'
    };
    return statusMap[status] || 'secondary';
}

function getBatteryIcon(level) {
    if (level >= 75) return '🔋';
    if (level >= 50) return '🔋';
    if (level >= 25) return '⚠';
    return '🪫';
}

function getRSSIStrength(rssi) {
    if (rssi > -50) return '(Excellent)';
    if (rssi > -60) return '(Good)';
    if (rssi > -70) return '(Fair)';
    if (rssi > -80) return '(Weak)';
    if (rssi > -100) return '(Very Weak)';
    return '(Critical)';
}

function estimateDistance(rssi) {
    // RSSI to distance conversion using log-distance path loss model
    // distance = 10^((TX_POWER - RSSI) / (10 * n))
    // TX_POWER = -40 dBm, n = 2.5 (indoor LoRa)
    const txPower = -40;
    const pathLossExponent = 2.5;
    const pathLoss = (rssi - txPower);
    const distance = Math.pow(10, pathLoss / (10 * pathLossExponent));
    
    // Clamp to reasonable range
    return Math.max(0.5, Math.min(50, distance));
}

function formatTimestamp(timestamp) {
    if (!timestamp) return 'Never';
    
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
