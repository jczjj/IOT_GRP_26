# Quick Start Guide

## Get Started in 3 Minutes

### Step 1: Install Dependencies
```bash
# Navigate to the project directory
cd "Application Server"

# Create virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Flask and dependencies
pip install -r requirements.txt
```

### Step 2: (Optional) Generate Dummy Images
```bash
# Install Pillow for image generation
pip install Pillow

# Generate placeholder images
python3 generate_dummy_images.py
```

### Step 3: Run the Server
```bash
# Start Flask development server
python3 app.py
```

You should see:
```
 * Running on http://127.0.0.1:5000
```

### Step 4: Open the Dashboard
Open your web browser and go to:
```
http://localhost:5000
```

## What You'll See

### Dashboard Features:
- **3D Topology View** (left side): Interactive 3D visualization of the facility
  - Yellow sphere = Gateway
  - Cyan spheres = Stationary Nodes (SN1, SN2, SN3)
  - Red cones = Patient Devices
  - Lines = RSSI signal connections

- **Device List** (right side): All patient devices with:
  - Battery level
  - Heart rate & temperature
  - Current location coordinates
  - Click any device card to see details

### Try These Actions:

1. **View Device Details**
   - Click any device card
   - See detailed information modal

2. **Request Location Update**
   - Open device details
   - Click "Update Location"
   - Simulates RSSI trilateration

3. **Request Image Capture**
   - Open device details for device_001, device_002, or device_004
   - Click "Request Image"
   - See relay path calculation
   - (Note: Requires dummy images generated or real integration)

4. **View Captured Image**
   - Click "View Image" for devices with images
   - Opens dedicated image viewer page

5. **Navigate the 3D View**
   - Click and drag to rotate
   - Scroll to zoom
   - Right-click drag to pan
   - Click "Reset View" to return to default

## Dummy Data Included

The app comes with realistic test data:

**Patients:**
- Margaret Smith (Room 101) - Device 001
- John Anderson (Room 102) - Device 002
- Evelyn Roberts (Room 103) - Device 003
- Robert Chen (Room 104) - Device 004

**Infrastructure:**
- LoRaWAN Gateway (center, ceiling-mounted)
- 3 Stationary Nodes (corners of facility)

## Next Steps

Once you've tested with dummy data:
2. **Set up your database** schema
3. **Replace dummy_data.py** with real data providers
4. **Connect to LoRa Network Server** API
5. **Deploy to production** (see README.md)

## Troubleshooting

**Port Already in Use?**
```bash
# Use a different port
python3 app.py --port 5001
```

Or modify app.py:
```python
app.run(host='0.0.0.0', port=5001, debug=True)
```

**Import Errors?**
```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

**No 3D Visualization?**
- Check browser console (F12) for errors
- Ensure internet connection (Three.js loads from CDN)
- Try Chrome or Firefox

**Need Help?**
- See full README.md for detailed documentation
- Check browser console for errors
- Review Flask terminal output

---

Happy monitoring!
