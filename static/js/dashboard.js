/**
 * Dashboard UI Controller
 * Handles device list, modals, and API interactions
 * Auto-updates with real calculated positions from RSSI trilateration
 */

let topology3d;
let selectedDevice = null;
let dataRefreshInterval = null;
let autoLocalizeInterval = null;
let jobConsoleVisible = false;
let deviceModalPollInterval = null;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize 3D topology
    try {
        topology3d = new Topology3D('canvas-container');
    } catch (e) {
        console.error('Error initializing Topology3D:', e);
    }

    // Load initial data
    try {
        loadData();
    } catch (e) {
        console.error('Error loading initial data:', e);
    }

    // Set up event listeners (defensive)
    try {
        setupEventListeners();
    } catch (e) {
        console.error('Error setting up event listeners:', e);
    }
    
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

    // Update all locations button
    const updateAllBtn = document.getElementById('updateAllLocationsBtn');
    if (updateAllBtn) {
        updateAllBtn.addEventListener('click', () => {
            updateAllLocations();
        });
    }

    // Job console close
    const closeJobConsole = document.getElementById('closeJobConsole');
    if (closeJobConsole) {
        closeJobConsole.addEventListener('click', () => {
            document.getElementById('jobConsole').style.display = 'none';
            jobConsoleVisible = false;
        });
    }
    
    // Jobs menu button to reopen console and list jobs
    const jobsMenuBtn = document.getElementById('jobsMenuBtn');
    if (jobsMenuBtn) {
        jobsMenuBtn.addEventListener('click', async () => {
            try {
                const resp = await fetch('/api/update-all-locations/jobs');
                const data = await resp.json();
                if (data.success) {
                    document.getElementById('jobConsole').style.display = 'block';
                    jobConsoleVisible = true;
                    renderJobsList(data.jobs);
                } else {
                    showToast('Failed to fetch jobs list', 'error');
                }
            } catch (e) {
                console.error('Error fetching jobs list:', e);
                showToast('Error fetching jobs list', 'error');
            }
        });
    }
    
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
    
    // Add inline logs container (will be populated asynchronously)
    const logsContainer = document.createElement('div');
    logsContainer.className = 'device-card-logs';
    logsContainer.style.marginTop = '8px';
    logsContainer.style.fontSize = '0.85rem';
    logsContainer.style.color = 'var(--text-gray)';
    logsContainer.innerHTML = '<div class="logs-loading">Loading logs...</div>';
    card.appendChild(logsContainer);

    // Fetch recent device job logs and render a short snippet
    (async () => {
        try {
            const resp = await fetch(`/api/device-job-status/${device.id}`);
            const data = await resp.json();
            if (data.success && Array.isArray(data.device_jobs) && data.device_jobs.length > 0) {
                // Gather logs from latest job entry
                const latest = data.device_jobs[0];
                const logs = latest.device_logs || [];
                if (logs.length === 0) {
                    logsContainer.innerHTML = '<div style="color:var(--text-muted)">No recent job logs</div>';
                } else {
                    const snippet = logs.slice(-3).map(l => `<div class="device-log-line">${escapeHtml(l)}</div>`).join('');
                    logsContainer.innerHTML = `<div style="font-weight:600;margin-bottom:4px;">Recent Logs</div>${snippet}`;
                }
            } else {
                logsContainer.innerHTML = '<div style="color:var(--text-muted)">No job activity</div>';
            }
        } catch (e) {
            logsContainer.innerHTML = '<div style="color:var(--text-danger)">Error loading logs</div>';
            console.debug('Error fetching device job logs:', e);
        }
    })();

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
                <h3>Job Status</h3>
                <div id="deviceJobStatus">Loading...</div>
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

    // Start polling for live device updates (RSSI and job status)
    startDeviceModalPolling(device.id);
}

function closeModal() {
    const modal = document.getElementById('deviceModal');
    modal.style.display = 'none';
    selectedDevice = null;
    stopDeviceModalPolling();
}


function startDeviceModalPolling(deviceId) {
    // clear any existing
    stopDeviceModalPolling();
    // poll device info and job status every 2 seconds while modal open
    deviceModalPollInterval = setInterval(async () => {
        try {
            // refresh device details (RSSI etc.)
            const resp = await fetch(`/api/device/${deviceId}`);
            const d = await resp.json();
            if (d.success && d.device) {
                // update selectedDevice and modal contents
                selectedDevice = d.device;
                // only update RSSI and small fields to avoid flicker
                updateModalRSSIAndStatus(d.device);
            }

            // fetch device job statuses
            const jresp = await fetch(`/api/device-job-status/${deviceId}`);
            const jdata = await jresp.json();
            if (jdata.success) {
                renderDeviceJobStatus(jdata.device_jobs);
            }
        } catch (e) {
            console.error('Error polling device modal data:', e);
        }
    }, 2000);
}


function stopDeviceModalPolling() {
    if (deviceModalPollInterval) {
        clearInterval(deviceModalPollInterval);
        deviceModalPollInterval = null;
    }
}


function updateModalRSSIAndStatus(device) {
    try {
        // update RSSI readings table if present
        const rssiReadings = device.rssi_readings || {};
        const rssiTable = document.querySelector('#modalBody .detail-section.full-width .detail-table');
        if (rssiTable) {
            // rebuild RSSI rows
            const rows = Object.entries(rssiReadings).map(([node, rssi]) => {
                const distance = estimateDistance(rssi);
                return `<tr><td><strong>${node.toUpperCase()}:</strong></td><td><code>${rssi}</code> dBm <span style="color: #999; font-size: 0.9em;">(${getRSSIStrength(rssi)} ~ ${distance.toFixed(1)}m)</span></td></tr>`;
            }).join('');
            rssiTable.querySelector('tbody')?.remove();
            // simple approach: find parent and replace innerHTML for RSSI block
            const rssiSection = Array.from(document.querySelectorAll('#modalBody .detail-section.full-width')).find(sec => sec.innerHTML.includes('RSSI Readings'));
            if (rssiSection) {
                // rebuild the table html
                const tableHtml = `<table class="detail-table">${rows}</table>`;
                // replace the section's innerHTML but preserve header
                const header = '<h3>📡 RSSI Readings from Anchors</h3>';
                rssiSection.innerHTML = header + tableHtml + (Object.keys(rssiReadings).length === 0 ? '<p style="color: #ff9800; padding: 10px;">No RSSI data yet. Trigger location request to collect RSSI readings.</p>' : '');
            }
        }
        // update basic status/battery in modal (if present)
        const statusBadges = document.querySelectorAll('#modalBody .badge');
        if (statusBadges && statusBadges.length>0) {
            // replace first badge text with status
            statusBadges[0].textContent = device.status || 'unknown';
        }
    } catch (e) {
        // non-fatal
        console.debug('Error updating modal RSSI/status:', e);
    }
}


function renderDeviceJobStatus(deviceJobs) {
    const container = document.getElementById('deviceJobStatus');
    if (!container) return;
    if (!deviceJobs || deviceJobs.length === 0) {
        container.innerHTML = '<div style="color:var(--text-gray)">No active jobs</div>';
        return;
    }
    // Render each job affecting this device. Show device-specific status prominently,
    // with the overall job status and timestamps secondary.
    const html = deviceJobs.map(j => {
        const logs = (j.device_logs || []).slice(-6).map(l => `<div class="job-log">${escapeHtml(l)}</div>`).join('');
        const deviceStatus = j.device_status || '—';
        const jobStatus = j.job_status || '—';
        const reqAt = j.requested_at ? `Requested: ${j.requested_at}` : '';
        const doneAt = j.completed_at ? `Completed: ${j.completed_at}` : '';

        return `
            <div style="padding:8px;background:var(--bg-light);border-radius:6px;margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="font-weight:700;">Device Status: <span style="color:var(--primary-color);">${escapeHtml(deviceStatus)}</span></div>
                    <div style="font-size:0.85rem;color:var(--text-gray);">Job: ${escapeHtml(j.job_id)} • ${escapeHtml(jobStatus)}</div>
                </div>
                <div style="font-size:0.85rem;color:var(--text-gray);margin-top:6px;">${escapeHtml(reqAt)} ${escapeHtml(doneAt)}</div>
                <div style="margin-top:8px;">${logs || '<div style="color:var(--text-gray)">No device logs yet</div>'}</div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

async function triggerLocalization(deviceId) {
    try {
        showToast('Starting device locate job...', 'info');

        // Create a per-device locate job which will be tracked separately
        const response = await fetch(`/api/locate-job/${deviceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timeout: 30 })
        });
        const data = await response.json();

        if (data.success && data.job_id) {
            showToast(`Locate job started (id: ${data.job_id}). Waiting for RSSI...`, 'success');
            // Ensure modal shows job status (modal polling will pick up the new job within next poll)
            // Force an immediate device-job-status fetch and render
            try {
                const jresp = await fetch(`/api/device-job-status/${deviceId}`);
                const jdata = await jresp.json();
                if (jdata.success) renderDeviceJobStatus(jdata.device_jobs);
            } catch (e) {
                console.debug('Could not fetch job immediately:', e);
            }
        } else {
            showToast('Failed to start locate job: ' + (data.error || 'unknown'), 'error');
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

async function updateAllLocations() {
    try {
        showToast('Queued update for all devices — starting...', 'info', 3000);

        // Show console immediately so user sees progress area and mark it visible
        const jobConsole = document.getElementById('jobConsole');
        if (jobConsole) {
            jobConsole.style.display = 'block';
            jobConsoleVisible = true;
            const body = document.getElementById('jobConsoleBody');
            if (body) body.innerHTML = `<div>Starting update job... awaiting server response</div>`;
        }

        const response = await fetch('/api/update-all-locations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timeout: 60 })
        });

        const data = await response.json();
        if (!data.success || !data.job_id) {
            showToast('Failed to start update job', 'error');
            return;
        }

        const jobId = data.job_id;
        showToast(`Update job started (id: ${jobId}). Polling status...`, 'info', 3000);

        // Poll job status until done/failed
        const pollInterval = 1000;
        const poll = setInterval(async () => {
            try {
                const stResp = await fetch(`/api/update-all-locations/status/${jobId}`);
                const stData = await stResp.json();
                if (!stData.success) {
                    showToast('Failed to fetch job status', 'error');
                    clearInterval(poll);
                    return;
                }

                const job = stData.job;
                try {
                    renderJobConsole(jobId, job);
                    if (jobConsoleVisible) {
                        document.getElementById('jobConsole').style.display = 'block';
                    }
                } catch (e) {
                    console.error('Error rendering job console:', e);
                }

                if (job.status === 'in_progress' || job.status === 'queued') {
                    // in progress — rendering above
                } else if (job.status === 'done') {
                    clearInterval(poll);
                    const updated = (job.updated_devices || []).length;
                    const pending = (job.pending_devices || []).length;
                    showToast(`Update complete. Updated: ${updated}, Pending: ${pending}`, 'success', 5000);
                    setTimeout(() => loadData(), 1200);
                } else if (job.status === 'failed') {
                    clearInterval(poll);
                    showToast(`Update failed: ${job.error || 'unknown'}`, 'error', 7000);
                    setTimeout(() => loadData(), 1200);
                }
            } catch (err) {
                console.error('Error polling job status:', err);
                clearInterval(poll);
                showToast('Error polling job status', 'error');
            }
        }, pollInterval);
    } catch (err) {
        console.error('Error updating all locations:', err);
        showToast('Error initiating update for all devices', 'error');
    }
}


function renderJobConsole(jobId, job) {
    const body = document.getElementById('jobConsoleBody');
    if (!body) return;
    // Header + progress
    const total = (job.device_ids || []).length;
    const updatedCount = (job.updated_devices || []).length;
    const percent = total > 0 ? Math.round((updatedCount / total) * 100) : 0;

    const header = `
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div><strong>Job ID:</strong> ${jobId}</div>
            <div><strong>Status:</strong> ${job.status}</div>
        </div>
        <div style="margin-top:6px;font-size:0.9rem;color:var(--text-gray);">Requested: ${job.requested_at} &nbsp; • &nbsp; Timeout: ${job.timeout_seconds}s</div>
        <div style="margin-top:8px;">
            <div class="progress" style="background:var(--bg-light);border-radius:6px;height:14px;overflow:hidden;">
                <div class="progress-bar" style="width:${percent}%;height:14px;background:linear-gradient(90deg,var(--primary-color),#3dbdb5);"></div>
            </div>
            <div style="font-size:0.85rem;color:var(--text-gray);margin-top:6px;">${updatedCount}/${total} devices updated — ${percent}%</div>
        </div>
        <hr/>
    `;

    // Devices table (compact)
    let devicesHtml = '<table class="job-table"><thead><tr><th>Device</th><th>Status</th><th>Last Updated</th></tr></thead><tbody>';
    const devices = job.devices || {};
    Object.keys(devices).forEach(did => {
        const dev = devices[did] || {};
        devicesHtml += `<tr><td>${did}</td><td>${dev.status || '—'}</td><td>${dev.last_updated || '—'}</td></tr>`;
    });
    devicesHtml += '</tbody></table>';

    // Job-level logs
    const jobLogs = (job.logs || []).slice(-20).map(l => `<div class="job-log">${escapeHtml(l)}</div>`).join('');

    // Expandable per-device logs area
    const deviceLogs = Object.keys(devices).map(did => {
        const dev = devices[did] || {};
        const logs = (dev.logs || []).map(l => `<div class="job-log">${escapeHtml(l)}</div>`).join('');
        return `<div style="margin-bottom:8px;"><strong>${did}</strong><div style="margin-top:6px;">${logs || '<span style="color:var(--text-gray)">No logs</span>'}</div></div>`;
    }).join('');

    body.innerHTML = header + devicesHtml + '<hr/>' + `<div class="job-logs"><h4>Job Logs</h4>${jobLogs}</div>` + '<hr/>' + `<div><h4>Device Logs</h4>${deviceLogs}</div>`;
}


function renderJobsList(jobs) {
    const body = document.getElementById('jobConsoleBody');
    if (!body) return;
    if (!Array.isArray(jobs) || jobs.length === 0) {
        body.innerHTML = '<div>No jobs found.</div>';
        return;
    }

    let html = '<div style="display:flex;flex-direction:column;gap:8px;">';
    jobs.sort((a,b) => (b.requested_at||'').localeCompare(a.requested_at||''));
    jobs.forEach(j => {
        html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px;background:var(--bg-light);border-radius:6px;">
            <div>
                <div style="font-weight:700">${j.job_id}</div>
                <div style="font-size:0.85rem;color:var(--text-gray)">${j.status} • ${j.updated_count || 0}/${j.num_devices || 0} • ${j.requested_at || ''}</div>
            </div>
            <div>
                <button class="btn btn-primary" onclick="openJob('${j.job_id}')">Open</button>
            </div>
        </div>`;
    });
    html += '</div>';
    body.innerHTML = html;
}

async function openJob(jobId) {
    try {
        const resp = await fetch(`/api/update-all-locations/status/${jobId}`);
        const data = await resp.json();
        if (data.success) {
            document.getElementById('jobConsole').style.display = 'block';
            jobConsoleVisible = true;
            renderJobConsole(jobId, data.job);
        } else {
            showToast('Failed to open job', 'error');
        }
    } catch (e) {
        console.error('Error opening job:', e);
        showToast('Error opening job', 'error');
    }
}

function escapeHtml(unsafe) {
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
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
    // d = 10^((TX_POWER - RSSI) / (10 * n))
    // RSSI closer to 0 = nearer, more negative = farther
    // TX_POWER = -40 dBm (reference at 1m), n = 2.5 (indoor LoRa)
    const txPower = -40;
    const pathLossExponent = 2.5;
    const pathLoss = txPower - rssi;
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
