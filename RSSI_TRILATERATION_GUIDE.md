# RSSI-Based Trilateration User Guide

## Overview

This guide explains how the Elderly Home Monitoring System uses **RSSI (Received Signal Strength Indicator)** to locate patient devices through **trilateration**.

### What is RSSI?
- **RSSI** = signal strength measured in dBm (decibel-milliwatts)
- Stronger signals (closer to 0) indicate devices nearer to the receiving antenna
- Weaker signals (more negative) indicate greater distance
- Example: -40 dBm (strong) vs -100 dBm (weak)

### What is Trilateration?
- Uses distances from **3+ known reference points** to calculate an unknown position
- Our system uses **4 stationary anchors**: Gateway + 3 anchor nodes
- **Weighted least-squares fitting** for robustness against noisy measurements

---

## System Architecture

### Stationary Reference Points (Anchors)

Your facility has 4 fixed anchor nodes with known coordinates:

```
Gateway:  (0m,    0m,    2.5m)
Anchor 1: (30m,   0m,    2.5m)
Anchor 2: (15m,   40m,   2.5m)
Anchor 3: (15m,   20m,   0.5m)
```

Facility dimensions: 30m × 40m × 5m (height)

### Data Flow

```
1. TTN Gateway receives message from device
2. Uplink message contains RSSI from gateway
3. App stores in rssi_readings table
4. Stationary nodes forward their own RSSI readings
5. User calls /api/localize/<device_id>
6. System converts RSSI → distance → position
7. Position updates device location in database
8. 3D visualization updates in real-time
```

---

## How RSSI is Converted to Distance

### Path Loss Model

We use the **Log-Distance Path Loss Model**:

$$\text{Distance} = 10^{(\text{TX\_POWER} - \text{RSSI}) / (10 \times n)}$$

Where:
- **TX_POWER** = -40 dBm (reference power at 1 meter)
- **RSSI** = measured signal strength (dBm)
- **n** = path loss exponent (2.0-4.0 depending on environment)

### Example Calculation

If a device sends a signal at -40 dBm TX power:
- At 1m away → RSSI = -40 dBm
- At 5m away → RSSI ≈ -57 dBm
- At 10m away → RSSI ≈ -63 dBm
- At 20m away → RSSI ≈ -69 dBm

### Configuration Parameters

Edit [`localization.py`](localization.py) to adjust:

```python
class RSSIToDistance:
    TX_POWER = -40           # Transmit power (typical: -40 to -20 dBm)
    PATH_LOSS_EXPONENT = 2.5  # 2.0-2.5 for indoor LoS, 3.0-4.0 for NLOS
    WALL_FADING = 3.0         # Extra attenuation per barrier (dB)
    MIN_DISTANCE = 0.5        # Clamp minimum
    MAX_DISTANCE = 50.0       # Clamp maximum
```

**Tuning Tips:**
- **PATH_LOSS_EXPONENT**: Lower (2.0-2.5) = clearer line-of-sight
  - Higher (3.0-4.0) = walls/obstacles between devices
  - Start at 2.5, adjust based on accuracy
- **TX_POWER**: Should match your device's actual TX power
  - Check device specs or measure with reference point

---

## Trilateration Algorithm

### Weighted Least-Squares

Given distance measurements from N anchors, solve:

$$\min_{\mathbf{x}} \sum_{i=1}^{N} w_i \|A_i \cdot \mathbf{x} - b_i\|^2$$

Where:
- **x** = unknown position [x, y, z]
- **w_i** = weight (confidence) of measurement i
- **A_i**, **b_i** = constraints from each anchor

### Confidence Weighting

Each measurement gets a confidence score (0.0-1.0) based on:

```python
confidence = (
    rssi_confidence * 0.5 +      # Signal strength quality
    distance_confidence * 0.3 +  # Optimal range (2-15m)
    count_confidence * 0.2        # Multiple measurements
)
```

Better measurements have more influence on final position.

### 2D vs 3D Localization

**3D Mode** (default):
- Estimates full x, y, z coordinates
- Requires good vertical separation of anchors
- Best accuracy with 4+ anchors

**2D Mode** (prefer_2d=True):
- Fixes z = 1.2m (wrist-worn device height)
- Uses only x, y components
- More stable with fewer anchors
- Better for mobile devices that stay at consistent height

---

## Using the Localization System

### Method 1: Python API (Programmatic)

```python
from device_manager import get_device_manager

dm = get_device_manager()

# Localize a device
result = dm.localize_device('patient-001', use_2d=False)

if result:
    print(f"Position: ({result['position']['x']:.2f}, "
                    f"{result['position']['y']:.2f}, "
                    f"{result['position']['z']:.2f})")
    print(f"Error: {result['residual_error']:.2f}m")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Used {result['num_measurements']} measurements")
```

### Method 2: REST API (HTTP)

**Basic localization:**
```bash
curl -X POST http://localhost:8080/api/localize/patient-001
```

**With 2D mode:**
```bash
curl -X POST "http://localhost:8080/api/localize/patient-001?use_2d=true"
```

**Response example:**
```json
{
  "success": true,
  "position": {
    "x": 14.5,
    "y": 19.8,
    "z": 1.2
  },
  "residual_error": 1.2,
  "confidence": 0.92,
  "accuracy": 0.87,
  "num_measurements": 4,
  "timestamp": "2026-03-05T10:30:45.123456"
}
```

### Method 3: Frontend (Dashboard)

The 3D visualization can be extended to call localization automatically:

```javascript
// In dashboard.js
async function localizeDevice(deviceId) {
    const response = await fetch(`/api/localize/${deviceId}`, {
        method: 'POST'
    });
    
    if (response.ok) {
        const data = await response.json();
        console.log('Device location:', data.position);
        // Update 3D visualization with new position
        topology3d.updateDevicePosition(deviceId, data.position);
    }
}
```

---

## Understanding Results

### Position
- **x, y, z**: Estimated coordinates in meters
- Origin at one corner of facility (typically gateway)

### Residual Error
- How well the measurements fit the calculated position
- Typical: 0.5-2.0m for good conditions
- If > 3m: Check RSSI data quality

### Confidence
- 0.0 = no confidence, 1.0 = perfect
- Based on RSSI strength, distance estimates, and count
- Typical: 0.7-0.95 in good conditions

### Accuracy
- Combined metric of confidence and residual error
- 0.0 = unreliable, 1.0 = excellent
- Use for filtering/weighting positions

### Num_Measurements
- How many anchors provided valid RSSI
- Need minimum 3 for 2D, 4 for 3D
- More is better (up to ~8)

---

## Workflow: Getting Up & Running

### Step 1: Verify Database Setup

```bash
python query_db.py
# Look for devices and rssi_readings
```

### Step 2: Test RSSI Data Collection

Ensure stationary nodes are sending RSSI. Update manually if needed:

```bash
curl -X POST http://localhost:8080/api/update-rssi/patient-001/gateway/-55
curl -X POST http://localhost:8080/api/update-rssi/patient-001/sn1/-65
curl -X POST http://localhost:8080/api/update-rssi/patient-001/sn2/-72
curl -X POST http://localhost:8080/api/update-rssi/patient-001/sn3/-68
```

### Step 3: Localize Device

```bash
curl -X POST http://localhost:8080/api/localize/patient-001
```

Check response for:
- ✅ `success: true`
- ✅ `num_measurements >= 3`
- ✅ `residual_error < 3`
- ✅ `confidence > 0.7`

### Step 4: Verify Position

```bash
curl http://localhost:8080/api/device/patient-001 | jq '.device.location_x, .device.location_y, .device.location_z'
```

Should show coordinates matching localization result.

---

## Tuning for Your Environment

### If accuracy is poor:

1. **Check RSSI data**
   - Are readings in expected range? (-30 to -100 dBm)
   - Do you have at least 4 measurements?
   - Use `query_db.py` to inspect

2. **Adjust path loss exponent**
   - Try 2.0 (fewer walls/obstacles)
   - Try 3.5 (many walls/obstacles)

3. **Verify anchor positions**
   - Confirm coordinates in stationary_nodes table
   - Use measuring tape to verify

4. **Check TX power**
   - Measure RSSI at known distance
   - Work backwards to find actual TX power

### Example: Room with Multiple Walls

```python
# In localization.py, increase path loss exponent
PATH_LOSS_EXPONENT = 3.2  # More attenuation
```

### Example: Open Concept Floor

```python
# Open space, clear LoS to all anchors
PATH_LOSS_EXPONENT = 2.0  # Less attenuation
```

---

## Advanced: Kalman Filtering (Smoothing)

For continuous tracking, use Kalman filtering to smooth position estimates:

```python
from localization import Trilateration

# Previous position
last_position = {'x': 14.5, 'y': 19.8, 'z': 1.2}

# New trilateration result
new_result = dm.localize_device('patient-001')

# Smooth with Kalman filter
filtered = Trilateration.kalman_filter(last_position, new_result)
print(f"Smoothed: {filtered}")
```

---

## Troubleshooting

### "Failed to localize: Ensure RSSI readings exist..."
- **Cause**: Fewer than 3 anchor measurements
- **Fix**: Update more RSSI readings manually, or wait for devices to report

### "Large residual_error (>5m)"
- **Cause**: Noisy RSSI or incorrect path loss exponent
- **Fix**: Check calibration, adjust PATH_LOSS_EXPONENT

### "Wrong positions (e.g., outside facility)"
- **Cause**: Bad RSSI data or anchor coordinates incorrect
- **Fix**: Verify database anchors with measuring tape

### "Position drifts over time"
- **Cause**: Multipath propagation causing RSSI variation
- **Fix**: Use Kalman filter, increase measurement samples

---

## Files Reference

| File | Purpose |
|------|---------|
| [`localization.py`](localization.py) | Core RSSI→distance, trilateration algorithms |
| [`device_manager.py`](device_manager.py) | Integration: localize_device() method |
| [`app.py`](app.py) | REST API: POST /api/localize/<device_id> |
| [`database.py`](database.py) | RSSI storage: rssi_readings table |

---

## Mathematics Reference

### Log-Distance Path Loss
$$RSSI(d) = P_0 - 10n\log_{10}(d)$$

Where:
- $P_0$ = RSSI at 1m reference (-40 dBm)
- $n$ = path loss exponent
- $d$ = distance in meters

### Least-Squares Solution
$$\hat{\mathbf{x}} = (A^T W A)^{-1} A^T W \mathbf{b}$$

Where:
- $A$ = distance constraint matrix
- $W$ = diagonal weight matrix (confidence scores)
- $\mathbf{b}$ = measured distances squared

---

## Next Steps

1. ✅ Collect RSSI data from your devices
2. ✅ Call `/api/localize/<device_id>` regularly
3. ✅ Verify accuracy in your specific environment
4. ✅ Tune PATH_LOSS_EXPONENT if needed
5. ✅ Integrate localization into 3D visualization
6. ✅ Implement continuous tracking with Kalman filter

Happy localizing! 📍
