/**
 * 3D Topology Visualization using Three.js
 * Displays stationary nodes and patient devices in 3D space with RSSI-based distances
 */

class Topology3D {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.deviceMeshes = new Map();
        this.nodeMeshes = new Map();
        this.deviceLabels = new Map();  // Track device labels for cleanup
        this.signalLines = [];
        this.distanceOverlays = [];
        this.showDistanceOverlays = false;
        
        // Facility center offset: shift both cuboid and anchors together
        this.facilityCenter = { x: 15, y: 0, z: 20 };
        // Uniform visual scaling for plotted entities (anchors/devices/links)
        // around the same center. This changes spacing proportionally only.
        this.worldScale = 2.6;
        // Visual scale for facility shell only. Node/device positions remain unchanged.
        this.cuboidScale = 0.6;
        this.baseCuboidWidth = 50;
        this.baseCuboidLength = 60;
        this.baseCuboidHeight = 5;
        this.cuboidWidth = this.baseCuboidWidth * this.cuboidScale;
        this.cuboidLength = this.baseCuboidLength * this.cuboidScale;
        this.cuboidHeight = this.baseCuboidHeight * this.cuboidScale;
        // Visual center of the cuboid (used for camera target, pivot, and axes helper)
        this.cuboidCenter = { x: this.facilityCenter.x, y: this.facilityCenter.y, z: this.facilityCenter.z };
        
        this.init();
    }

    toWorldPosition(location) {
        return {
            x: this.facilityCenter.x + (location.x * this.worldScale),
            y: this.facilityCenter.y + (location.z * this.worldScale),
            z: this.facilityCenter.z + (location.y * this.worldScale)
        };
    }

    init() {
        // Create scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1a1a2e);

        // Create camera
        const aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(75, aspect, 0.1, 1000);
        // Default overview camera aimed at cuboid center
        this.camera.position.set(34, 14, 44);
        this.camera.lookAt(this.cuboidCenter.x, this.cuboidCenter.y, this.cuboidCenter.z);

        // Create renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.container.appendChild(this.renderer.domElement);

        // Add orbit controls
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.target.set(this.cuboidCenter.x, this.cuboidCenter.y, this.cuboidCenter.z);
        this.controls.update();
        this.controls.saveState();

        // Add lights
        this.addLights();

        // Add facility floor and walls
        this.createFacility();

        // Add grid helper - sized to the scaled cuboid
        const gridSize = Math.max(this.cuboidWidth, this.cuboidLength);
        const gridDivisions = Math.max(8, Math.round(gridSize));
        const gridHelper = new THREE.GridHelper(gridSize, gridDivisions, 0x444444, 0x222222);
        gridHelper.position.set(this.cuboidCenter.x, this.cuboidCenter.y, this.cuboidCenter.z);
        this.scene.add(gridHelper);

        // Add axes helper
        const axesHelper = new THREE.AxesHelper(5);
        axesHelper.position.set(this.cuboidCenter.x, this.cuboidCenter.y, this.cuboidCenter.z);
        this.scene.add(axesHelper);

        // Handle window resize
        window.addEventListener('resize', () => this.onWindowResize());

        // Start animation loop
        this.animate();
    }

    addLights() {
        // Ambient light
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        this.scene.add(ambientLight);

        // Directional light
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(10, 20, 10);
        this.scene.add(directionalLight);

        // Point light for dramatic effect
        const pointLight = new THREE.PointLight(0x4ecdc4, 0.5);
        pointLight.position.set(15, 15, 20);
        this.scene.add(pointLight);
    }

    createFacility() {
        // Floor (scaled proportionally from 30m x 40m)
        const halfWidth = this.cuboidWidth / 2;
        const halfLength = this.cuboidLength / 2;
        const floorGeometry = new THREE.PlaneGeometry(this.cuboidWidth, this.cuboidLength);
        const floorMaterial = new THREE.MeshStandardMaterial({
            color: 0x2d2d44,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.8
        });
        const floor = new THREE.Mesh(floorGeometry, floorMaterial);
        floor.rotation.x = -Math.PI / 2;
        floor.position.set(this.facilityCenter.x, this.facilityCenter.y, this.facilityCenter.z);
        this.scene.add(floor);

        // Walls (wireframe) centered on the same cuboid center
        const wallMaterial = new THREE.LineBasicMaterial({ color: 0x444466 });

        const points = [
            new THREE.Vector3(this.facilityCenter.x - halfWidth, this.facilityCenter.y, this.facilityCenter.z - halfLength),
            new THREE.Vector3(this.facilityCenter.x + halfWidth, this.facilityCenter.y, this.facilityCenter.z - halfLength),
            new THREE.Vector3(this.facilityCenter.x + halfWidth, this.facilityCenter.y, this.facilityCenter.z + halfLength),
            new THREE.Vector3(this.facilityCenter.x - halfWidth, this.facilityCenter.y, this.facilityCenter.z + halfLength),
            new THREE.Vector3(this.facilityCenter.x - halfWidth, this.facilityCenter.y, this.facilityCenter.z - halfLength),
            new THREE.Vector3(this.facilityCenter.x - halfWidth, this.facilityCenter.y + this.cuboidHeight, this.facilityCenter.z - halfLength),
            new THREE.Vector3(this.facilityCenter.x + halfWidth, this.facilityCenter.y + this.cuboidHeight, this.facilityCenter.z - halfLength),
            new THREE.Vector3(this.facilityCenter.x + halfWidth, this.facilityCenter.y, this.facilityCenter.z - halfLength),
            new THREE.Vector3(this.facilityCenter.x + halfWidth, this.facilityCenter.y + this.cuboidHeight, this.facilityCenter.z - halfLength),
            new THREE.Vector3(this.facilityCenter.x + halfWidth, this.facilityCenter.y + this.cuboidHeight, this.facilityCenter.z + halfLength),
            new THREE.Vector3(this.facilityCenter.x + halfWidth, this.facilityCenter.y, this.facilityCenter.z + halfLength),
            new THREE.Vector3(this.facilityCenter.x + halfWidth, this.facilityCenter.y + this.cuboidHeight, this.facilityCenter.z + halfLength),
            new THREE.Vector3(this.facilityCenter.x - halfWidth, this.facilityCenter.y + this.cuboidHeight, this.facilityCenter.z + halfLength),
            new THREE.Vector3(this.facilityCenter.x - halfWidth, this.facilityCenter.y, this.facilityCenter.z + halfLength),
            new THREE.Vector3(this.facilityCenter.x - halfWidth, this.facilityCenter.y + this.cuboidHeight, this.facilityCenter.z + halfLength),
            new THREE.Vector3(this.facilityCenter.x - halfWidth, this.facilityCenter.y + this.cuboidHeight, this.facilityCenter.z - halfLength)
        ];
        
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const walls = new THREE.Line(geometry, wallMaterial);
        this.scene.add(walls);
    }

    addStationaryNode(node) {
        const existing = this.nodeMeshes.get(node.id);
        if (existing) {
            // Keep anchor positions synchronized with latest backend coordinates.
            const worldPos = this.toWorldPosition(node.location);
            existing.position.set(
                worldPos.x,
                worldPos.y,
                worldPos.z
            );
            existing.userData = {
                ...(existing.userData || {}),
                logicalLocation: { ...node.location },
                nodeType: node.type,
                nodeId: node.id
            };
            this.refreshDistanceOverlays();
            return;
        }

        // Different appearance for gateway vs regular nodes
        const isGateway = node.type === 'gateway';
        const color = isGateway ? 0xffe66d : 0x4ecdc4;
        const size = isGateway ? 0.8 : 0.6;

        // Create node mesh
        const geometry = new THREE.SphereGeometry(size, 32, 32);
        const material = new THREE.MeshStandardMaterial({
            color: color,
            emissive: color,
            emissiveIntensity: 0.3,
            metalness: 0.5,
            roughness: 0.3
        });
        const mesh = new THREE.Mesh(geometry, material);
        // Apply facility center offset to anchor positions
        const worldPos = this.toWorldPosition(node.location);
        mesh.position.set(
            worldPos.x,
            worldPos.y,
            worldPos.z
        );

        // Add pulsing animation
        mesh.userData = { 
            originalScale: size,
            pulseSpeed: isGateway ? 0.02 : 0.015,
            id: node.id,
            logicalLocation: { ...node.location },
            nodeType: node.type,
            nodeId: node.id
        };

        this.scene.add(mesh);
        this.nodeMeshes.set(node.id, mesh);

        // Add label
        this.addLabel(node.name, mesh.position, 1.5, 0xffffff);

        // Add range circle (on floor)
        this.addRangeCircle(mesh.position, (isGateway ? 15 : 10) * this.cuboidScale, color);
        this.refreshDistanceOverlays();
    }

    addDevice(device) {
        // Create device mesh (smaller, red)
        const geometry = new THREE.ConeGeometry(0.4, 0.8, 8);
        const material = new THREE.MeshStandardMaterial({
            color: 0xff6b6b,
            emissive: 0xff6b6b,
            emissiveIntensity: 0.4,
            metalness: 0.3,
            roughness: 0.5
        });
        const mesh = new THREE.Mesh(geometry, material);
        // Apply facility center offset to device position (same as anchors)
        const worldPos = this.toWorldPosition(device.location);
        mesh.position.set(
            worldPos.x,
            worldPos.y,
            worldPos.z
        );
        mesh.rotation.x = Math.PI; // Point upward

        mesh.userData = {
            id: device.id,
            device: device
        };

        this.scene.add(mesh);
        this.deviceMeshes.set(device.id, mesh);

        // Add label and store reference for cleanup
        const label = this.createLabel(device.patient_name, mesh.position, 1.2, 0xff6b6b);
        this.deviceLabels.set(device.id, label);

        // Draw RSSI signal lines to stationary nodes
        this.drawRSSILines(device);
        this.refreshDistanceOverlays();
    }

    clearDistanceOverlays() {
        this.distanceOverlays.forEach(entry => {
            if (entry.sprite) {
                this.scene.remove(entry.sprite);
            }
            if (entry.line) {
                this.scene.remove(entry.line);
            }
        });
        this.distanceOverlays = [];
    }

    refreshDistanceOverlays() {
        if (!this.showDistanceOverlays) {
            this.clearDistanceOverlays();
            return;
        }

        this.clearDistanceOverlays();

        const stationaryNodes = Array.from(this.nodeMeshes.values())
            .filter(mesh => (mesh.userData?.nodeType || 'anchor') !== 'gateway');

        this.deviceMeshes.forEach(deviceMesh => {
            const device = deviceMesh.userData?.device;
            if (!device || !device.location) {
                return;
            }

            stationaryNodes.forEach(nodeMesh => {
                const nodeLoc = nodeMesh.userData?.logicalLocation;
                if (!nodeLoc) {
                    return;
                }

                // Compute metric distance from logical coordinates (meters), not scaled world coords.
                const dx = Number(device.location.x) - Number(nodeLoc.x);
                const dy = Number(device.location.y) - Number(nodeLoc.y);
                const dz = Number(device.location.z || 0) - Number(nodeLoc.z || 0);
                const distanceMeters = Math.sqrt((dx * dx) + (dy * dy) + (dz * dz));

                const start = deviceMesh.position.clone();
                const end = nodeMesh.position.clone();
                const midpoint = start.clone().add(end).multiplyScalar(0.5);

                const lineGeometry = new THREE.BufferGeometry().setFromPoints([start, end]);
                const lineMaterial = new THREE.LineDashedMaterial({
                    color: 0xffffff,
                    dashSize: 0.5,
                    gapSize: 0.3,
                    transparent: true,
                    opacity: 0.22
                });
                const line = new THREE.Line(lineGeometry, lineMaterial);
                line.computeLineDistances();
                this.scene.add(line);

                const text = `${nodeMesh.userData?.nodeId || 'node'}: ${distanceMeters.toFixed(2)}m`;
                const sprite = this.createLabel(text, midpoint, 0.7, 0xffffff);
                sprite.scale.set(3.6, 0.9, 1);

                this.distanceOverlays.push({ sprite, line });
            });
        });
    }

    setDistanceOverlayVisible(visible) {
        this.showDistanceOverlays = Boolean(visible);
        this.refreshDistanceOverlays();
    }

    toggleDistanceOverlay() {
        this.setDistanceOverlayVisible(!this.showDistanceOverlays);
        return this.showDistanceOverlays;
    }

    drawRSSILines(device) {
        // Draw lines from device to each stationary node with RSSI strength
        Object.entries(device.rssi_readings).forEach(([nodeId, rssi]) => {
            const nodeMesh = this.nodeMeshes.get(nodeId);
            if (!nodeMesh) return;

            // Color intensity based on signal strength
            // Stronger signal (less negative) = brighter line
            const strength = Math.max(0, 1 + (rssi + 90) / 40); // Normalize -90 to -50
            const color = new THREE.Color().setHSL(0.6 - (strength * 0.3), 1, strength * 0.5);
            const worldPos = this.toWorldPosition(device.location);

            const points = [
                new THREE.Vector3(
                    worldPos.x,
                    worldPos.y,
                    worldPos.z
                ),
                nodeMesh.position.clone()
            ];

            const geometry = new THREE.BufferGeometry().setFromPoints(points);
            const material = new THREE.LineBasicMaterial({
                color: color,
                transparent: true,
                opacity: 0.3 + (strength * 0.4)
            });
            const line = new THREE.Line(geometry, material);
            this.scene.add(line);
            this.signalLines.push(line);
        });
    }

    addLabel(text, position, offset, color) {
        const label = this.createLabel(text, position, offset, color);
        return label;
    }

    createLabel(text, position, offset, color) {
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.width = 256;
        canvas.height = 64;

        context.fillStyle = 'rgba(0, 0, 0, 0.7)';
        context.fillRect(0, 0, canvas.width, canvas.height);

        context.font = 'Bold 20px Arial';
        context.fillStyle = '#' + color.toString(16).padStart(6, '0');
        context.textAlign = 'center';
        context.fillText(text, 128, 40);

        const texture = new THREE.CanvasTexture(canvas);
        const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
        const sprite = new THREE.Sprite(spriteMaterial);
        
        sprite.position.set(position.x, position.y + offset, position.z);
        sprite.scale.set(4, 1, 1);
        
        this.scene.add(sprite);
        return sprite;
    }

    addRangeCircle(position, radius, color) {
        const geometry = new THREE.RingGeometry(radius - 0.1, radius, 64);
        const material = new THREE.MeshBasicMaterial({
            color: color,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.1
        });
        const ring = new THREE.Mesh(geometry, material);
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(position.x, 0.1, position.z);
        this.scene.add(ring);
    }

    clearDevices() {
        this.clearDistanceOverlays();

        // Remove all device meshes
        this.deviceMeshes.forEach(mesh => {
            this.scene.remove(mesh);
        });
        this.deviceMeshes.clear();

        // Remove all device labels
        this.deviceLabels.forEach(label => {
            this.scene.remove(label);
        });
        this.deviceLabels.clear();

        // Remove signal lines
        this.signalLines.forEach(line => {
            this.scene.remove(line);
        });
        this.signalLines = [];
    }

    updateDevices(devices) {
        this.clearDevices();
        devices.forEach(device => this.addDevice(device));
        this.refreshDistanceOverlays();
    }

    animate() {
        requestAnimationFrame(() => this.animate());

        // Pulse stationary nodes
        this.nodeMeshes.forEach(mesh => {
            const pulse = Math.sin(Date.now() * mesh.userData.pulseSpeed) * 0.1 + 1;
            mesh.scale.set(pulse, pulse, pulse);
        });

        // Rotate device cones slightly
        this.deviceMeshes.forEach(mesh => {
            mesh.rotation.y += 0.01;
        });

        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }

    onWindowResize() {
        this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    }

    resetView() {
        this.camera.position.set(34, 14, 44);
        this.controls.target.set(this.cuboidCenter.x, this.cuboidCenter.y, this.cuboidCenter.z);
        this.controls.update();
    }
}

// Export for use in dashboard.js
window.Topology3D = Topology3D;
