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
        this.signalLines = [];
        
        this.init();
    }

    init() {
        // Create scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1a1a2e);

        // Create camera
        const aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(75, aspect, 0.1, 1000);
        this.camera.position.set(25, 25, 35);
        this.camera.lookAt(15, 0, 20);

        // Create renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.container.appendChild(this.renderer.domElement);

        // Add orbit controls
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;

        // Add lights
        this.addLights();

        // Add facility floor and walls
        this.createFacility();

        // Add grid helper
        const gridHelper = new THREE.GridHelper(40, 40, 0x444444, 0x222222);
        gridHelper.position.y = 0;
        this.scene.add(gridHelper);

        // Add axes helper
        const axesHelper = new THREE.AxesHelper(5);
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
        // Floor (30m x 40m)
        const floorGeometry = new THREE.PlaneGeometry(30, 40);
        const floorMaterial = new THREE.MeshStandardMaterial({
            color: 0x2d2d44,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.8
        });
        const floor = new THREE.Mesh(floorGeometry, floorMaterial);
        floor.rotation.x = -Math.PI / 2;
        floor.position.set(15, 0, 20);
        this.scene.add(floor);

        // Walls (wireframe)
        const wallMaterial = new THREE.LineBasicMaterial({ color: 0x444466 });
        
        // Create wall outline
        const points = [
            new THREE.Vector3(0, 0, 0),
            new THREE.Vector3(30, 0, 0),
            new THREE.Vector3(30, 0, 40),
            new THREE.Vector3(0, 0, 40),
            new THREE.Vector3(0, 0, 0),
            new THREE.Vector3(0, 5, 0),
            new THREE.Vector3(30, 5, 0),
            new THREE.Vector3(30, 0, 0),
            new THREE.Vector3(30, 5, 0),
            new THREE.Vector3(30, 5, 40),
            new THREE.Vector3(30, 0, 40),
            new THREE.Vector3(30, 5, 40),
            new THREE.Vector3(0, 5, 40),
            new THREE.Vector3(0, 0, 40),
            new THREE.Vector3(0, 5, 40),
            new THREE.Vector3(0, 5, 0)
        ];
        
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const walls = new THREE.Line(geometry, wallMaterial);
        this.scene.add(walls);
    }

    addStationaryNode(node) {
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
        mesh.position.set(node.location.x, node.location.z, node.location.y);

        // Add pulsing animation
        mesh.userData = { 
            originalScale: size,
            pulseSpeed: isGateway ? 0.02 : 0.015,
            id: node.id
        };

        this.scene.add(mesh);
        this.nodeMeshes.set(node.id, mesh);

        // Add label
        this.addLabel(node.name, mesh.position, 1.5, 0xffffff);

        // Add range circle (on floor)
        this.addRangeCircle(mesh.position, isGateway ? 15 : 10, color);
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
        mesh.position.set(device.location.x, device.location.z, device.location.y);
        mesh.rotation.x = Math.PI; // Point upward

        mesh.userData = {
            id: device.id,
            device: device
        };

        this.scene.add(mesh);
        this.deviceMeshes.set(device.id, mesh);

        // Add label
        this.addLabel(device.patient_name, mesh.position, 1.2, 0xff6b6b);

        // Draw RSSI signal lines to stationary nodes
        this.drawRSSILines(device);
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

            const points = [
                new THREE.Vector3(device.location.x, device.location.z, device.location.y),
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
        // Remove all device meshes
        this.deviceMeshes.forEach(mesh => {
            this.scene.remove(mesh);
        });
        this.deviceMeshes.clear();

        // Remove signal lines
        this.signalLines.forEach(line => {
            this.scene.remove(line);
        });
        this.signalLines = [];
    }

    updateDevices(devices) {
        this.clearDevices();
        devices.forEach(device => this.addDevice(device));
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
        this.camera.position.set(25, 25, 35);
        this.camera.lookAt(15, 0, 20);
        this.controls.reset();
    }
}

// Export for use in dashboard.js
window.Topology3D = Topology3D;
