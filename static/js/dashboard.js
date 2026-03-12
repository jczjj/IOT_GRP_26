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
// Single active job poll controller so multiple polls don't fight each other
let activeJobPollInterval = null;
let activeJobFocusedId = null;
const autoLocalizationState = new Map();
// Current device jobs shown in the device modal (used by tab handler)
let currentDeviceJobsForModal = null;
// Currently opened job id inside the device modal detail pane (for live updates)
let currentDeviceJobDetailId = null;
// Poll interval for the currently-open device job detail
let deviceJobDetailPollInterval = null;

function getValidRssiEntries(rssiReadings) {
    return Object.entries(rssiReadings || {}).filter(([, rssi]) => Number.isFinite(rssi));
}

function getValidRssiCount(rssiReadings) {
    return getValidRssiEntries(rssiReadings).length;
}

function buildRssiSignature(device) {
    const entries = getValidRssiEntries(device.rssi_readings)
        .sort(([left], [right]) => left.localeCompare(right));
    if (entries.length === 0) {
        return null;
    }
    return entries.map(([nodeId, rssi]) => `${nodeId}:${rssi}`).join('|');
}

const ALL_ANCHOR_IDS = ['gateway', 'sn1', 'sn2', 'sn3'];

function hasAllFreshRssi(rssiReadings) {
    return ALL_ANCHOR_IDS.every(id => Number.isFinite((rssiReadings || {})[id]));
}

function shouldAutoLocalize(device) {
    if (!hasAllFreshRssi(device.rssi_readings)) {
        return false;
    }

    const signature = buildRssiSignature(device);
    if (!signature) {
        return false;
    }

    const state = autoLocalizationState.get(device.id);
    if (!state) {
        return true;
    }

    if (state.inFlight) {
        return false;
    }

    return state.lastSignature !== signature;
}

function markAutoLocalizationStart(device) {
    autoLocalizationState.set(device.id, {
        lastSignature: buildRssiSignature(device),
        inFlight: true,
    });
}

function markAutoLocalizationComplete(deviceId, signatureOverride = null) {
    const previous = autoLocalizationState.get(deviceId) || {};
    autoLocalizationState.set(deviceId, {
        lastSignature: signatureOverride ?? previous.lastSignature ?? null,
        inFlight: false,
    });
}

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
                // Stop any active focused job polling so the jobs list remains visible
                if (activeJobPollInterval) {
                    clearInterval(activeJobPollInterval);
                    activeJobPollInterval = null;
                    activeJobFocusedId = null;
                }
                const resp = await fetch('/api/update-all-locations/jobs');
                const data = await resp.json();
                if (data.success) {
                    document.getElementById('jobConsole').style.display = 'flex';
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
                if (shouldAutoLocalize(device)) {
                    localizeDeviceIfReady(device);
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
                if (shouldAutoLocalize(device)) {
                    localizeDeviceIfReady(device);
                    localizationAttempted = true;
                }
            });
        }
    } catch (error) {
        console.error('Error in auto-localization:', error);
    }
}

async function localizeDeviceIfReady(deviceOrId) {
    try {
        const device = typeof deviceOrId === 'string'
            ? { id: deviceOrId, rssi_readings: {} }
            : deviceOrId;
        const deviceId = device.id;
        if (!device || !shouldAutoLocalize(device)) {
            return;
        }

        markAutoLocalizationStart(device);

        // Attempt trilateration with current RSSI data
        const response = await fetch(`/api/localize/${deviceId}`, {
            method: 'POST'
        });
        const data = await response.json();
        const signature = buildRssiSignature(device);
        
        if (data.success) {
            console.log(`✓ Auto-localized ${deviceId}: (${data.position.x.toFixed(2)}, ${data.position.y.toFixed(2)}, ${data.position.z.toFixed(2)})m`);
            markAutoLocalizationComplete(deviceId, signature);
            
            // If modal is open and showing this device, update it
            if (selectedDevice && selectedDevice.id === deviceId) {
                const refreshed = { ...selectedDevice, location: data.position };
                selectedDevice = refreshed;
                updateModalRSSIAndStatus(refreshed);
            }
        } else {
            markAutoLocalizationComplete(deviceId, signature);
        }
    } catch (error) {
        console.error(`Error auto-localizing ${deviceId}:`, error);
        markAutoLocalizationComplete(deviceId);
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
    const rssiCount = getValidRssiCount(device.rssi_readings);
    const localizationReady = hasAllFreshRssi(device.rssi_readings);
    const readyIndicator = localizationReady ? '✓ Ready' : `${rssiCount}/4`;
    const readyClass = localizationReady ? 'badge-success' : 'badge-warning';
    
    card.innerHTML = `
        <div class="device-header">
            <h3>${device.patient_name}</h3>
            <span class="status-pill status-${statusClass}">${device.status}</span>
        </div>
        <div class="device-info">
            <div class="info-row">
                <span class="label">Device ID</span>
                <span class="value mono">${device.id}</span>
            </div>
            <div class="info-row">
                <span class="label">Room</span>
                <span class="value">${device.room}</span>
            </div>
            <div class="info-row">
                <span class="label">Position</span>
                <span class="value mono">(${device.location.x.toFixed(1)}, ${device.location.y.toFixed(1)}, ${device.location.z.toFixed(1)}) m</span>
            </div>
            <div class="info-row">
                <span class="label">RSSI Nodes</span>
                <span class="value"><span class="badge badge-${readyClass}">${readyIndicator}</span></span>
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
                    const snippet = logs.slice(-3).map(l => formatLogHtml(l, 'device-log-line')).join('');
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
    const rssiCount = getValidRssiCount(rssiReadings);
    const localizationReady = rssiCount >= 3;
    
    // Build detailed info with localization data
    modalBody.innerHTML = `
        <div class="detail-grid">
            <div class="detail-section">
                <h3>Patient Information</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>Name</strong></td>
                        <td>${device.patient_name}</td>
                    </tr>
                    <tr>
                        <td><strong>Room</strong></td>
                        <td>${device.room}</td>
                    </tr>
                    <tr>
                        <td><strong>Device ID</strong></td>
                        <td><code>${device.id}</code></td>
                    </tr>
                </table>
            </div>

            <div class="detail-section">
                <h3>Device Status</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>Status</strong></td>
                        <td><span class="status-pill status-${getStatusClass(device.status)}">${device.status}</span></td>
                    </tr>
                    <tr>
                        <td><strong>Last Uplink</strong></td>
                        <td>${formatTimestamp(device.last_uplink)}</td>
                    </tr>
                </table>
            </div>

            <div class="detail-section">
                <h3>Location Job</h3>
                <div id="deviceJobStatus">Loading...</div>
            </div>

            <div class="detail-section">
                <h3>Calculated Position</h3>
                <table class="detail-table">
                    <tr>
                        <td><strong>X</strong></td>
                        <td><code>${device.location.x.toFixed(3)}</code> m</td>
                    </tr>
                    <tr>
                        <td><strong>Y</strong></td>
                        <td><code>${device.location.y.toFixed(3)}</code> m</td>
                    </tr>
                    <tr>
                        <td><strong>Z (Height)</strong></td>
                        <td><code>${device.location.z.toFixed(3)}</code> m</td>
                    </tr>
                    <tr>
                        <td><strong>Anchor Nodes</strong></td>
                        <td>
                            <span class="badge badge-${localizationReady ? 'success' : 'warning'}">
                                ${rssiCount}/4
                            </span>
                            ${localizationReady ? ' ✓ Ready' : ' Need more data'}
                        </td>
                    </tr>
                </table>
            </div>
            
            <div class="detail-section full-width">
                <h3>RSSI Readings</h3>
                <table class="detail-table">
                    ${getValidRssiEntries(rssiReadings).map(([node, rssi]) => {
                        const distance = estimateDistance(node, rssi);
                        return `
                        <tr>
                            <td><strong>${node.toUpperCase()}:</strong></td>
                            <td>
                                <code>${rssi}</code> dBm 
                                <span style="color: #999; font-size: 0.9em;">
                                    (${getRSSIStrength(calibrateRssi(node, rssi))} ~ ${distance.toFixed(1)}m)
                                </span>
                            </td>
                        </tr>
                    `;
                    }).join('')}
                </table>
                ${rssiCount === 0 ? '<p class="empty-note">No RSSI data yet. Trigger a location request to collect readings.</p>' : ''}
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
    currentDeviceJobDetailId = null;
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
    }, 1000);
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
            const rows = getValidRssiEntries(rssiReadings).map(([node, rssi]) => {
                const distance = estimateDistance(node, rssi);
                return `<tr><td><strong>${node.toUpperCase()}:</strong></td><td><code>${rssi}</code> dBm <span style="color: #999; font-size: 0.9em;">(${getRSSIStrength(calibrateRssi(node, rssi))} ~ ${distance.toFixed(1)}m)</span></td></tr>`;
            }).join('');
            rssiTable.querySelector('tbody')?.remove();
            // simple approach: find parent and replace innerHTML for RSSI block
            const rssiSection = Array.from(document.querySelectorAll('#modalBody .detail-section.full-width')).find(sec => sec.innerHTML.includes('RSSI Readings'));
            if (rssiSection) {
                // rebuild the table html
                const tableHtml = `<table class="detail-table">${rows}</table>`;
                // replace the section's innerHTML but preserve header
                const header = '<h3>📡 RSSI Readings from Anchors</h3>';
                rssiSection.innerHTML = header + tableHtml + (getValidRssiCount(rssiReadings) === 0 ? '<p style="color: #ff9800; padding: 10px;">No RSSI data yet. Trigger location request to collect RSSI readings.</p>' : '');
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
        // enable locate button when no active jobs
        const locateBtn = document.getElementById('locateBtn');
        if (locateBtn) locateBtn.disabled = false;
        return;
    }
    // Render as a compact jobs list. Clicking "Open" will show logs in the
    // main job console popup so modal stays compact.
    currentDeviceJobsForModal = deviceJobs;

    const jobListHtml = deviceJobs.map(j => {
        const jobStatus = j.job_status || j.status || '—';
        const updatedCount = j.updated_count || (j.updated_devices || []).length || 0;
        const numDevices = j.num_devices || (j.device_ids || []).length || 0;
        return `<div style="padding:8px;background:var(--bg-light);border-radius:6px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">
                    <div style="min-width:0;">
                        <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px">${escapeHtml(j.job_id)}</div>
                        <div style="font-size:0.85rem;color:var(--text-gray)">${escapeHtml(jobStatus)} • ${updatedCount}/${numDevices} • ${escapeHtml(j.requested_at || '')}</div>
                    </div>
                    <div>
                        <button class="btn btn-tertiary" onclick="openDeviceJobPopup('${escapeHtml(j.job_id)}')">Open</button>
                    </div>
                </div>`;
    }).join('');

    container.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px;">${jobListHtml}</div>`;

    // If any job for this device is queued/in_progress, mark the locate button visually
    // but do NOT set the `disabled` attribute so clicks still fire and can surface errors.
    const hasActive = deviceJobs.some(j => ['queued','in_progress'].includes(j.job_status || j.status));
    const locateBtn = document.getElementById('locateBtn');
    if (locateBtn) {
        if (hasActive) {
            locateBtn.classList.add('btn-disabled');
            locateBtn.setAttribute('aria-disabled', 'true');
            locateBtn.title = 'Localization in progress for this device';
        } else {
            locateBtn.classList.remove('btn-disabled');
            locateBtn.removeAttribute('aria-disabled');
            locateBtn.title = '';
        }
    }
    // If a job detail pane is open, refresh its contents so logs update in real-time
    if (currentDeviceJobDetailId) {
        try { showDeviceJobDetail(currentDeviceJobDetailId); } catch (e) { console.debug('Error refreshing device job detail:', e); }
    }
}

// Show logs/details for a specific job in the device modal.
function showDeviceJobDetail(jobId) {
    // Track the active detail and start a focused poll against the full job
    // status endpoint so logs update exactly like the main Job Console.
    currentDeviceJobDetailId = jobId;

    // Clear any existing focused poll
    if (deviceJobDetailPollInterval) {
        clearInterval(deviceJobDetailPollInterval);
        deviceJobDetailPollInterval = null;
    }

    const detail = document.getElementById('deviceJobDetail');
    if (!detail) return;

    async function fetchAndRender() {
        try {
            const resp = await fetch(`/api/update-all-locations/status/${encodeURIComponent(jobId)}`);
            const data = await resp.json();
            if (!data.success || !data.job) {
                detail.innerHTML = '<div style="color:var(--text-gray)">Job not found</div>';
                return;
            }
            const job = data.job;
            const deviceId = selectedDevice ? selectedDevice.id : null;
            const dev = deviceId ? (job.devices || {})[deviceId] || {} : {};

            const deviceStatus = dev.status || dev.device_status || '—';
            const reqAt = job.requested_at ? `Requested: ${job.requested_at}` : '';
            const doneAt = job.completed_at ? `Completed: ${job.completed_at}` : '';

            const logsArr = (dev.logs || dev.device_logs || []);
            const logs = logsArr.slice().map(l => formatLogHtml(l, 'job-log')).join('') || '<div style="color:var(--text-gray)">No device logs yet</div>';

            detail.innerHTML = `
                <div style="padding:8px;background:var(--bg-light);border-radius:6px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div style="font-weight:700;">Device Status: <span style="color:var(--primary-color);">${escapeHtml(deviceStatus)}</span></div>
                        <div style="font-size:0.85rem;color:var(--text-gray);">Job: ${escapeHtml(jobId)} • ${escapeHtml(job.status || '')}</div>
                    </div>
                    <div style="font-size:0.85rem;color:var(--text-gray);margin-top:6px;">${escapeHtml(reqAt)} ${escapeHtml(doneAt)}</div>
                    <div style="margin-top:8px;">${logs}</div>
                </div>
            `;

            // Stop polling when job completes
            if (!['queued', 'in_progress'].includes(job.status)) {
                if (deviceJobDetailPollInterval) {
                    clearInterval(deviceJobDetailPollInterval);
                    deviceJobDetailPollInterval = null;
                    currentDeviceJobDetailId = null;
                }
            }
        } catch (e) {
            console.debug('Error fetching job detail status:', e);
        }
    }

    fetchAndRender();
    deviceJobDetailPollInterval = setInterval(fetchAndRender, 1000);
}

// Open device job logs in the main Job Console popup so modal stays compact.
function openDeviceJobPopup(jobId) {
    if (!currentDeviceJobsForModal) return;
    const job = currentDeviceJobsForModal.find(j => j.job_id === jobId);
    if (!job) return;

    const jobConsole = document.getElementById('jobConsole');
    const jobBody = document.getElementById('jobConsoleBody');
    const headerH3 = document.querySelector('#jobConsole .job-console-header h3');
    if (jobConsole && jobBody) {
        // Update header and body with job-specific content
        if (headerH3) headerH3.textContent = `Job: ${job.job_id}`;
        const jobLogs = (job.device_logs || []).slice().map(l => formatLogHtml(l, 'job-log')).join('') || '<div style="color:var(--text-gray)">No device logs yet</div>';
        const deviceStatus = job.device_status || '—';
        const reqAt = job.requested_at ? `Requested: ${job.requested_at}` : '';
        const doneAt = job.completed_at ? `Completed: ${job.completed_at}` : '';

        jobBody.innerHTML = `
            <div style="padding:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="font-weight:700;">Device Status: <span style="color:var(--primary-color);">${escapeHtml(deviceStatus)}</span></div>
                    <div style="font-size:0.85rem;color:var(--text-gray);">Job: ${escapeHtml(job.job_id)} • ${escapeHtml(job.job_status || job.status || '')}</div>
                </div>
                <div style="font-size:0.85rem;color:var(--text-gray);margin-top:6px;">${escapeHtml(reqAt)} ${escapeHtml(doneAt)}</div>
                <hr/>
                <div>${jobLogs}</div>
            </div>
        `;

        jobConsole.style.display = 'flex';
        jobConsoleVisible = true;

        // Start a focused poll for this job so the console updates in real-time,
        // mirroring the behavior of `openJob()`.
        if (activeJobPollInterval) {
            clearInterval(activeJobPollInterval);
            activeJobPollInterval = null;
            activeJobFocusedId = null;
        }
        activeJobFocusedId = jobId;
        activeJobPollInterval = setInterval(async () => {
            try {
                const sresp = await fetch(`/api/update-all-locations/status/${jobId}`);
                const sdata = await sresp.json();
                if (sdata.success) {
                    renderJobConsole(jobId, sdata.job);
                    if (!['queued','in_progress'].includes(sdata.job.status)) {
                        clearInterval(activeJobPollInterval);
                        activeJobPollInterval = null;
                        activeJobFocusedId = null;
                    }
                }
            } catch (e) {
                console.error('Error polling opened job from device modal:', e);
                clearInterval(activeJobPollInterval);
                activeJobPollInterval = null;
                activeJobFocusedId = null;
            }
        }, 1000);
    }
}

async function triggerLocalization(deviceId) {
    try {
        // Check device job status first; if a locate job is already active,
        // inform the user rather than attempting to start another.
        try {
            const statusResp = await fetch(`/api/device-job-status/${deviceId}`);
            const statusData = await statusResp.json();
            if (statusData.success && Array.isArray(statusData.device_jobs)) {
                const hasActive = statusData.device_jobs.some(j => ['queued','in_progress'].includes(j.job_status || j.status));
                if (hasActive) {
                    showToast('Localization in progress, please try again later', 'error', 7000);
                    return;
                }
            }
        } catch (e) {
            // ignore errors from status check and proceed
            console.debug('Could not check device job status before triggering localization:', e);
        }

        showToast('Starting device locate job...', 'info');

        // Create a per-device locate job which will be tracked separately
        const response = await fetch(`/api/locate-job/${deviceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timeout: 30 })
        });
        let data;
        try {
            data = await response.json();
        } catch (e) {
            showToast('Failed to start locate job', 'error', 7000);
            return;
        }

        if (response.ok && data.success && data.job_id) {
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
            showToast('Failed to start locate job: ' + (data && data.error ? data.error : response.statusText || 'unknown'), 'error', 7000);
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
            jobConsole.style.display = 'flex';
            jobConsoleVisible = true;
            const body = document.getElementById('jobConsoleBody');
            if (body) body.innerHTML = `<div>Starting update job... awaiting server response</div>`;
        }

        const response = await fetch('/api/update-all-locations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timeout: 60 })
        });

        let data;
        try {
            data = await response.json();
        } catch (e) {
            showToast('Failed to start update job', 'error');
            return;
        }

        if (!response.ok || !data.success || !data.job_id) {
            const msg = data && data.error ? data.error : response.statusText || 'Failed to start update job';
            showToast(msg, 'error', 7000);
            return;
        }

        const jobId = data.job_id;
        showToast(`Update job started (id: ${jobId}). Polling status...`, 'info', 3000);

        // Poll job status until done/failed. Clear any existing job poll first
        if (activeJobPollInterval) {
            clearInterval(activeJobPollInterval);
            activeJobPollInterval = null;
            activeJobFocusedId = null;
        }
        activeJobFocusedId = jobId;
        const pollInterval = 1000;
        activeJobPollInterval = setInterval(async () => {
            try {
                const stResp = await fetch(`/api/update-all-locations/status/${jobId}`);
                const stData = await stResp.json();
                if (!stData.success) {
                    showToast('Failed to fetch job status', 'error');
                    clearInterval(activeJobPollInterval);
                    activeJobPollInterval = null;
                    activeJobFocusedId = null;
                    return;
                }

                const job = stData.job;
                try {
                    renderJobConsole(jobId, job);
                    if (jobConsoleVisible) {
                        document.getElementById('jobConsole').style.display = 'flex';
                    }
                } catch (e) {
                    console.error('Error rendering job console:', e);
                }

                if (job.status === 'in_progress' || job.status === 'queued') {
                    // in progress — rendering above
                } else if (job.status === 'done') {
                    clearInterval(activeJobPollInterval);
                    activeJobPollInterval = null;
                    activeJobFocusedId = null;
                    const updated = (job.updated_devices || []).length;
                    const pending = (job.pending_devices || []).length;
                    showToast(`Update complete. Updated: ${updated}, Pending: ${pending}`, 'success', 5000);
                    setTimeout(() => loadData(), 1200);
                } else if (job.status === 'failed') {
                    clearInterval(activeJobPollInterval);
                    activeJobPollInterval = null;
                    activeJobFocusedId = null;
                    showToast(`Update failed: ${job.error || 'unknown'}`, 'error', 7000);
                    setTimeout(() => loadData(), 1200);
                }
            } catch (err) {
                console.error('Error polling job status:', err);
                clearInterval(activeJobPollInterval);
                activeJobPollInterval = null;
                activeJobFocusedId = null;
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
    // Preserve user's scroll position relative to bottom so updates don't
    // force the view to jump to the top while the user is reading logs.
    const prevScrollTop = body.scrollTop;
    const prevScrollHeight = body.scrollHeight;
    const prevClientHeight = body.clientHeight;
    const distanceFromBottom = prevScrollHeight - prevScrollTop - prevClientHeight;
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
    const jobLogs = (job.logs || []).slice(-20).map(l => formatLogHtml(l, 'job-log')).join('');

    // Expandable per-device logs area
    const deviceLogs = Object.keys(devices).map(did => {
        const dev = devices[did] || {};
        const logs = (dev.logs || []).map(l => formatLogHtml(l, 'job-log')).join('');
        return `<div style="margin-bottom:8px;"><strong>${did}</strong><div style="margin-top:6px;">${logs || '<span style="color:var(--text-gray)">No logs</span>'}</div></div>`;
    }).join('');

    const newHtml = header + devicesHtml + '<hr/>' + `<div class="job-logs"><h4>Job Logs</h4>${jobLogs}</div>` + '<hr/>' + `<div><h4>Device Logs</h4>${deviceLogs}</div>`;
    body.innerHTML = newHtml;

    // Restore scroll to keep user's relative position from bottom stable.
    const newScrollHeight = body.scrollHeight;
    const newClientHeight = body.clientHeight;
    const newScrollTop = Math.max(0, newScrollHeight - newClientHeight - distanceFromBottom);
    body.scrollTop = newScrollTop;
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
        // When user opens a job, stop any existing automatic job polling so
        // the console sticks to the job the user requested.
        if (activeJobPollInterval) {
            clearInterval(activeJobPollInterval);
            activeJobPollInterval = null;
            activeJobFocusedId = null;
        }

        const resp = await fetch(`/api/update-all-locations/status/${jobId}`);
        const data = await resp.json();
        if (data.success) {
            document.getElementById('jobConsole').style.display = 'flex';
            jobConsoleVisible = true;
            renderJobConsole(jobId, data.job);

            // start a focused poll for this opened job so the modal stays live
            activeJobFocusedId = jobId;
            activeJobPollInterval = setInterval(async () => {
                try {
                    const sresp = await fetch(`/api/update-all-locations/status/${jobId}`);
                    const sdata = await sresp.json();
                    if (sdata.success) {
                        renderJobConsole(jobId, sdata.job);
                        if (!['queued','in_progress'].includes(sdata.job.status)) {
                            clearInterval(activeJobPollInterval);
                            activeJobPollInterval = null;
                            activeJobFocusedId = null;
                        }
                    }
                } catch (e) {
                    console.error('Error polling opened job:', e);
                    clearInterval(activeJobPollInterval);
                    activeJobPollInterval = null;
                    activeJobFocusedId = null;
                }
            }, 1000);
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

// Format a log line into HTML with a colored level tag when present.
function formatLogHtml(unsafe, containerClass = 'job-log') {
    if (!unsafe) return `<div class="${containerClass}"></div>`;
    const raw = String(unsafe);
    const m = raw.match(/^\s*\[([A-Za-z]+)\]\s*(.*)$/);
    let level, rest;
    if (m) {
        level = m[1].toUpperCase();
        rest = m[2] || '';
    } else {
        // infer level from keywords when no explicit prefix exists
        rest = raw;
        const low = raw.toLowerCase();
        // Heuristic keyword matching: remove generic 'rssi' from success to avoid
        // classifying heartbeat/waiting messages as success. Keep 'received' and
        // 'localized' as success indicators.
        if (/\b(success|ok|received|localized)\b/.test(low)) level = 'SUCCESS';
        else if (/\b(fail|failed|error|unable|abandoned|no response|no rssi)\b/.test(low)) level = 'FAILURE';
        else if (/\b(warn|warning|low)\b/.test(low)) level = 'WARNING';
        else level = 'INFO';
    }

    let levelClass = 'log-info';
    if (level === 'SUCCESS' || level === 'OK') levelClass = 'log-success';
    else if (level === 'FAIL' || level === 'FAILURE' || level === 'ERROR') levelClass = 'log-failure';
    else if (level === 'WARN' || level === 'WARNING') levelClass = 'log-warning';
    // render: <div class="job-log"><span class="log-level log-info">[INFO]</span> escaped remainder</div>
    return `<div class="${containerClass}"><span class="log-level ${levelClass}">[${escapeHtml(level)}]</span> ${escapeHtml(rest)}</div>`;
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

// Per-node RSSI calibration offsets — must mirror NODE_RSSI_CALIBRATION in anchor_layout.py
const NODE_RSSI_CALIBRATION = {};  // cleared: base model now calibrated for this room

function calibrateRssi(nodeId, rssi) {
    return rssi + (NODE_RSSI_CALIBRATION[nodeId] || 0);
}

function estimateDistance(nodeId, rssi) {
    const calibratedRssi = calibrateRssi(nodeId, rssi);
    const referenceRssiAtOneMeter = -50;
    const pathLossExponent = 3.5;   // indoor same-floor small room
    const pathLoss = referenceRssiAtOneMeter - calibratedRssi;
    const distance = Math.pow(10, pathLoss / (10 * pathLossExponent));
    // Clamp to room diagonal (15m x 15m => ~21m)
    return Math.max(0.25, Math.min(21, distance));
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
    const icons = { error: '✖', success: '✓', info: 'ℹ', warning: '⚠' };
    const icon = icons[type] || '';
    // use innerHTML so we can style the icon separately and keep message readable
    toast.innerHTML = `<span style="margin-right:8px;font-weight:700">${icon}</span><span>${escapeHtml(String(message))}</span>`;
    toast.className = `toast toast-${type} show`;
    // log errors to console for easier debugging
    if (type === 'error') console.error('UI Toast Error:', message);

    setTimeout(() => {
        toast.className = 'toast';
        toast.innerHTML = '';
    }, duration);
}
