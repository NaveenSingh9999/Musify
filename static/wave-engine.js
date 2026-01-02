/**
 * 🎵 Musify Wave Engine v1.0
 * The Ultimate Audio Experience Platform
 * 
 * A revolutionary audio processing engine designed for the most natural,
 * immersive, and emotionally engaging listening experience.
 */

class WaveEngine {
    constructor() {
        this.audioContext = null;
        this.sourceNode = null;
        this.isInitialized = false;
        this.isEnabled = true;
        this.isBypassed = false;
        this.audioElement = null;
        
        // Processing modules
        this.modules = {};
        
        // Current settings
        this.settings = {
            preset: 'balanced',
            harmonic: {
                enabled: true,
                overtones: 0.3,
                transients: 0.5,
                subBass: 0.3,
                air: 0.4
            },
            spatial: {
                enabled: true,
                room: 'studio',
                width: 1.0,
                depth: 0.5,
                height: 0.3
            },
            dynamics: {
                enabled: true,
                mode: 'balanced', // pure, enhanced, balanced, night, compressed
                ceiling: -1,
                ratio: 4,
                attack: 10,
                release: 100
            },
            color: {
                enabled: true,
                warmth: 0.5,
                brightness: 0.5,
                body: 0.5,
                air: 0.5,
                punch: 0.5
            },
            output: {
                volume: 1.0,
                limiterEnabled: true
            }
        };
        
        // Presets
        this.presets = {
            'studio': { harmonic: { overtones: 0.2, transients: 0.3 }, color: { warmth: 0.4, brightness: 0.6 }, spatial: { room: 'studio', width: 1.0 } },
            'analog': { harmonic: { overtones: 0.5, transients: 0.4 }, color: { warmth: 0.7, brightness: 0.4 }, spatial: { room: 'analog', width: 1.1 } },
            'concert': { harmonic: { overtones: 0.4, transients: 0.5 }, color: { warmth: 0.5, brightness: 0.5 }, spatial: { room: 'concert', width: 1.3 } },
            'club': { harmonic: { overtones: 0.3, transients: 0.6 }, color: { warmth: 0.6, brightness: 0.5 }, spatial: { room: 'club', width: 0.9 } },
            'basshead': { harmonic: { overtones: 0.3, subBass: 0.7 }, color: { warmth: 0.6, body: 0.8, punch: 0.7 }, spatial: { width: 1.0 } },
            'vocal': { harmonic: { overtones: 0.4, transients: 0.3 }, color: { warmth: 0.5, brightness: 0.6, body: 0.6 }, spatial: { width: 0.95 } },
            'audiophile': { harmonic: { overtones: 0.15, transients: 0.2, air: 0.5 }, color: { warmth: 0.45, brightness: 0.55 }, spatial: { room: 'studio', width: 1.0 } },
            'night': { harmonic: { overtones: 0.2, transients: 0.2 }, color: { warmth: 0.7, brightness: 0.3 }, dynamics: { mode: 'night' }, spatial: { width: 0.9 } },
            'balanced': { harmonic: { overtones: 0.3, transients: 0.4 }, color: { warmth: 0.5, brightness: 0.5 }, spatial: { width: 1.0 } }
        };
        
        // Visualization data
        this.visualData = {
            spectrum: new Float32Array(256),
            waveform: new Float32Array(256),
            loudness: 0,
            peak: 0,
            stereoWidth: 0
        };
        
        // Event callbacks
        this.callbacks = {};
    }
    
    /**
     * Initialize the Wave Engine with an audio element
     */
    async init(audioElement) {
        if (this.isInitialized) return this;
        
        this.audioElement = audioElement;
        
        // Set crossOrigin to allow processing of streaming audio
        // Note: This must be set BEFORE any src is loaded
        if (!audioElement.crossOrigin) {
            audioElement.crossOrigin = 'anonymous';
        }
        
        // Create audio context
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
            latencyHint: 'playback',
            sampleRate: 48000
        });
        
        // Create source from audio element
        try {
            this.sourceNode = this.audioContext.createMediaElementSource(audioElement);
        } catch (e) {
            // Source may already be connected from a previous init attempt
            console.warn('Wave Engine: Source already connected or error:', e.message);
            if (!this.sourceNode) {
                // Can't proceed without source node
                console.error('Wave Engine: Cannot create source node');
                return this;
            }
        }
        
        // Initialize all processing modules
        await this._initModules();
        
        // Connect the audio graph
        this._connectGraph();
        
        this.isInitialized = true;
        this._emit('initialized', { sampleRate: this.audioContext.sampleRate });
        
        console.log('🎵 Wave Engine initialized');
        return this;
    }
    
    /**
     * Initialize all processing modules
     */
    async _initModules() {
        const ctx = this.audioContext;
        
        // === HARMONIC RESTORATION ENGINE ===
        this.modules.harmonic = {
            // Low shelf for warmth/sub-bass
            lowShelf: ctx.createBiquadFilter(),
            // High shelf for air frequencies
            highShelf: ctx.createBiquadFilter(),
            // Presence peak for overtones
            presencePeak: ctx.createBiquadFilter(),
            // Transient enhancer (compressor in parallel)
            transientComp: ctx.createDynamicsCompressor(),
            transientGain: ctx.createGain(),
            // Sub-bass enhancer
            subBassFilter: ctx.createBiquadFilter(),
            subBassGain: ctx.createGain(),
            // Air frequencies
            airFilter: ctx.createBiquadFilter(),
            airGain: ctx.createGain(),
            // Mix
            dryGain: ctx.createGain(),
            wetGain: ctx.createGain()
        };
        
        // Configure harmonic filters
        const h = this.modules.harmonic;
        h.lowShelf.type = 'lowshelf';
        h.lowShelf.frequency.value = 200;
        h.lowShelf.gain.value = 0;
        
        h.highShelf.type = 'highshelf';
        h.highShelf.frequency.value = 8000;
        h.highShelf.gain.value = 0;
        
        h.presencePeak.type = 'peaking';
        h.presencePeak.frequency.value = 3000;
        h.presencePeak.Q.value = 1.5;
        h.presencePeak.gain.value = 0;
        
        h.transientComp.threshold.value = -24;
        h.transientComp.knee.value = 6;
        h.transientComp.ratio.value = 4;
        h.transientComp.attack.value = 0.001;
        h.transientComp.release.value = 0.05;
        h.transientGain.gain.value = 0;
        
        h.subBassFilter.type = 'lowpass';
        h.subBassFilter.frequency.value = 80;
        h.subBassFilter.Q.value = 1;
        h.subBassGain.gain.value = 0;
        
        h.airFilter.type = 'highpass';
        h.airFilter.frequency.value = 12000;
        h.airFilter.Q.value = 0.7;
        h.airGain.gain.value = 0;
        
        h.dryGain.gain.value = 1;
        h.wetGain.gain.value = 0;
        
        // === SPATIAL AUDIO MATRIX ===
        this.modules.spatial = {
            // Stereo widener using mid-side processing
            splitter: ctx.createChannelSplitter(2),
            merger: ctx.createChannelMerger(2),
            leftGain: ctx.createGain(),
            rightGain: ctx.createGain(),
            midGain: ctx.createGain(),
            sideGain: ctx.createGain(),
            // Convolver for room simulation
            convolver: ctx.createConvolver(),
            convolverGain: ctx.createGain(),
            dryGain: ctx.createGain(),
            // Delay for depth
            delayL: ctx.createDelay(0.1),
            delayR: ctx.createDelay(0.1),
            delayGain: ctx.createGain(),
            // Output
            output: ctx.createGain()
        };
        
        const s = this.modules.spatial;
        s.leftGain.gain.value = 1;
        s.rightGain.gain.value = 1;
        s.midGain.gain.value = 1;
        s.sideGain.gain.value = 1;
        s.convolverGain.gain.value = 0;
        s.dryGain.gain.value = 1;
        s.delayL.delayTime.value = 0.01;
        s.delayR.delayTime.value = 0.012;
        s.delayGain.gain.value = 0;
        s.output.gain.value = 1;
        
        // Generate room impulse responses
        await this._generateRoomImpulses();
        
        // === INTELLIGENT DYNAMIC PROCESSOR ===
        this.modules.dynamics = {
            // Input gain
            inputGain: ctx.createGain(),
            // Main compressor
            compressor: ctx.createDynamicsCompressor(),
            // Makeup gain
            makeupGain: ctx.createGain(),
            // Limiter
            limiter: ctx.createDynamicsCompressor(),
            // Output
            output: ctx.createGain()
        };
        
        const d = this.modules.dynamics;
        d.inputGain.gain.value = 1;
        d.compressor.threshold.value = -18;
        d.compressor.knee.value = 12;
        d.compressor.ratio.value = 3;
        d.compressor.attack.value = 0.02;
        d.compressor.release.value = 0.15;
        d.makeupGain.gain.value = 1;
        d.limiter.threshold.value = -1;
        d.limiter.knee.value = 0;
        d.limiter.ratio.value = 20;
        d.limiter.attack.value = 0.001;
        d.limiter.release.value = 0.05;
        d.output.gain.value = 1;
        
        // === ACOUSTIC COLOR SYSTEM ===
        this.modules.color = {
            // 5-band EQ for tonal shaping
            lowBand: ctx.createBiquadFilter(),      // Body (100-300Hz)
            lowMidBand: ctx.createBiquadFilter(),   // Warmth (200-800Hz)
            midBand: ctx.createBiquadFilter(),       // Presence (1-4kHz)
            highMidBand: ctx.createBiquadFilter(),  // Brightness (4-8kHz)
            highBand: ctx.createBiquadFilter(),     // Air (10kHz+)
            // Saturation (waveshaper)
            saturator: ctx.createWaveShaper(),
            saturatorGain: ctx.createGain(),
            // Mix
            output: ctx.createGain()
        };
        
        const c = this.modules.color;
        c.lowBand.type = 'peaking';
        c.lowBand.frequency.value = 150;
        c.lowBand.Q.value = 1;
        c.lowBand.gain.value = 0;
        
        c.lowMidBand.type = 'peaking';
        c.lowMidBand.frequency.value = 400;
        c.lowMidBand.Q.value = 1;
        c.lowMidBand.gain.value = 0;
        
        c.midBand.type = 'peaking';
        c.midBand.frequency.value = 2000;
        c.midBand.Q.value = 1;
        c.midBand.gain.value = 0;
        
        c.highMidBand.type = 'peaking';
        c.highMidBand.frequency.value = 6000;
        c.highMidBand.Q.value = 1;
        c.highMidBand.gain.value = 0;
        
        c.highBand.type = 'highshelf';
        c.highBand.frequency.value = 10000;
        c.highBand.gain.value = 0;
        
        c.saturator.curve = this._makeSaturationCurve(0.3);
        c.saturatorGain.gain.value = 0;
        c.output.gain.value = 1;
        
        // === VISUALIZER ===
        this.modules.visualizer = {
            analyser: ctx.createAnalyser(),
            analyserR: ctx.createAnalyser() // For stereo analysis
        };
        
        const v = this.modules.visualizer;
        v.analyser.fftSize = 2048;
        v.analyser.smoothingTimeConstant = 0.8;
        v.analyserR.fftSize = 2048;
        v.analyserR.smoothingTimeConstant = 0.8;
        
        // === MASTER OUTPUT ===
        this.modules.master = {
            gain: ctx.createGain(),
            analyser: ctx.createAnalyser()
        };
        
        this.modules.master.gain.gain.value = 1;
        this.modules.master.analyser.fftSize = 256;
    }
    
    /**
     * Generate room impulse responses for spatial processing
     */
    async _generateRoomImpulses() {
        const ctx = this.audioContext;
        const sampleRate = ctx.sampleRate;
        
        // Create a simple synthetic reverb impulse
        const length = sampleRate * 1.5; // 1.5 seconds
        const impulse = ctx.createBuffer(2, length, sampleRate);
        
        for (let channel = 0; channel < 2; channel++) {
            const data = impulse.getChannelData(channel);
            for (let i = 0; i < length; i++) {
                // Exponential decay with some early reflections
                const t = i / sampleRate;
                const decay = Math.exp(-3 * t);
                const earlyReflection = i < sampleRate * 0.05 ? 
                    (Math.random() * 2 - 1) * 0.3 * Math.exp(-20 * t) : 0;
                const lateReverb = (Math.random() * 2 - 1) * decay * 0.5;
                data[i] = earlyReflection + lateReverb;
            }
        }
        
        this.modules.spatial.convolver.buffer = impulse;
        
        // Store room presets
        this.roomImpulses = {
            studio: this._createRoomImpulse(0.3, 2),
            analog: this._createRoomImpulse(0.5, 3),
            concert: this._createRoomImpulse(1.5, 1.5),
            club: this._createRoomImpulse(0.8, 4),
            theater: this._createRoomImpulse(1.2, 2),
            open: this._createRoomImpulse(0.2, 1)
        };
    }
    
    /**
     * Create a room impulse response
     */
    _createRoomImpulse(reverbTime, density) {
        const ctx = this.audioContext;
        const sampleRate = ctx.sampleRate;
        const length = sampleRate * reverbTime;
        const impulse = ctx.createBuffer(2, length, sampleRate);
        
        for (let channel = 0; channel < 2; channel++) {
            const data = impulse.getChannelData(channel);
            for (let i = 0; i < length; i++) {
                const t = i / sampleRate;
                const decay = Math.exp(-density * t);
                data[i] = (Math.random() * 2 - 1) * decay;
            }
        }
        
        return impulse;
    }
    
    /**
     * Create saturation curve for warm analog character
     */
    _makeSaturationCurve(amount) {
        const samples = 44100;
        const curve = new Float32Array(samples);
        const deg = Math.PI / 180;
        
        for (let i = 0; i < samples; i++) {
            const x = (i * 2) / samples - 1;
            // Soft clipping with adjustable amount
            curve[i] = (3 + amount) * x * 20 * deg / (Math.PI + amount * Math.abs(x));
        }
        
        return curve;
    }
    
    /**
     * Connect the audio processing graph
     */
    _connectGraph() {
        const h = this.modules.harmonic;
        const s = this.modules.spatial;
        const d = this.modules.dynamics;
        const c = this.modules.color;
        const v = this.modules.visualizer;
        const m = this.modules.master;
        
        // Disconnect any existing connections
        try {
            this.sourceNode.disconnect();
        } catch (e) {
            // May not be connected yet
        }
        
        if (this.isBypassed) {
            // Bypass mode - direct connection to destination
            this.sourceNode.connect(this.audioContext.destination);
            console.log('🎵 Wave Engine: Bypass mode (direct output)');
            return;
        }
        
        // Source → Harmonic Restoration
        this.sourceNode.connect(h.lowShelf);
        h.lowShelf.connect(h.highShelf);
        h.highShelf.connect(h.presencePeak);
        
        // Parallel transient processing
        h.presencePeak.connect(h.transientComp);
        h.transientComp.connect(h.transientGain);
        h.presencePeak.connect(h.dryGain);
        
        // Sub-bass enhancement
        h.presencePeak.connect(h.subBassFilter);
        h.subBassFilter.connect(h.subBassGain);
        
        // Air enhancement  
        h.presencePeak.connect(h.airFilter);
        h.airFilter.connect(h.airGain);
        
        // Mix harmonic processing
        h.dryGain.connect(h.wetGain);
        h.transientGain.connect(h.wetGain);
        h.subBassGain.connect(h.wetGain);
        h.airGain.connect(h.wetGain);
        
        // Harmonic → Spatial
        h.wetGain.connect(s.splitter);
        
        // Stereo processing
        s.splitter.connect(s.leftGain, 0);
        s.splitter.connect(s.rightGain, 1);
        
        // Delays for depth
        s.leftGain.connect(s.delayL);
        s.rightGain.connect(s.delayR);
        s.delayL.connect(s.delayGain);
        s.delayR.connect(s.delayGain);
        
        // Direct path
        s.leftGain.connect(s.merger, 0, 0);
        s.rightGain.connect(s.merger, 0, 1);
        
        // Convolver reverb
        s.merger.connect(s.convolver);
        s.convolver.connect(s.convolverGain);
        s.merger.connect(s.dryGain);
        
        // Mix spatial
        s.dryGain.connect(s.output);
        s.convolverGain.connect(s.output);
        s.delayGain.connect(s.output);
        
        // Spatial → Dynamics
        s.output.connect(d.inputGain);
        d.inputGain.connect(d.compressor);
        d.compressor.connect(d.makeupGain);
        d.makeupGain.connect(d.limiter);
        d.limiter.connect(d.output);
        
        // Dynamics → Color
        d.output.connect(c.lowBand);
        c.lowBand.connect(c.lowMidBand);
        c.lowMidBand.connect(c.midBand);
        c.midBand.connect(c.highMidBand);
        c.highMidBand.connect(c.highBand);
        
        // Saturation path
        c.highBand.connect(c.saturator);
        c.saturator.connect(c.saturatorGain);
        c.highBand.connect(c.output);
        c.saturatorGain.connect(c.output);
        
        // Color → Visualizer → Master
        c.output.connect(v.analyser);
        v.analyser.connect(m.gain);
        m.gain.connect(m.analyser);
        m.analyser.connect(this.audioContext.destination);
        
        console.log('🔊 Audio graph connected');
    }
    
    /**
     * Apply a preset
     */
    setPreset(presetName) {
        const preset = this.presets[presetName];
        if (!preset) {
            console.warn(`Preset "${presetName}" not found`);
            return;
        }
        
        this.settings.preset = presetName;
        
        // Apply preset settings
        if (preset.harmonic) {
            Object.assign(this.settings.harmonic, preset.harmonic);
            this._updateHarmonic();
        }
        
        if (preset.spatial) {
            Object.assign(this.settings.spatial, preset.spatial);
            this._updateSpatial();
        }
        
        if (preset.dynamics) {
            Object.assign(this.settings.dynamics, preset.dynamics);
            this._updateDynamics();
        }
        
        if (preset.color) {
            Object.assign(this.settings.color, preset.color);
            this._updateColor();
        }
        
        this._emit('presetChanged', { preset: presetName, settings: this.settings });
        console.log(`🎚️ Preset applied: ${presetName}`);
    }
    
    /**
     * Update harmonic restoration settings
     */
    setHarmonic(options) {
        Object.assign(this.settings.harmonic, options);
        this._updateHarmonic();
        this._emit('harmonicChanged', this.settings.harmonic);
    }
    
    _updateHarmonic() {
        const h = this.modules.harmonic;
        const s = this.settings.harmonic;
        
        if (!h || !this.isInitialized) return;
        
        // Overtones - boost presence frequencies
        h.presencePeak.gain.value = s.overtones * 6;
        
        // Transients - parallel compression amount
        h.transientGain.gain.value = s.transients * 0.5;
        
        // Sub-bass enhancement
        h.subBassGain.gain.value = (s.subBass || 0.3) * 0.4;
        h.lowShelf.gain.value = (s.subBass || 0.3) * 4;
        
        // Air frequencies
        h.airGain.gain.value = (s.air || 0.4) * 0.3;
        h.highShelf.gain.value = (s.air || 0.4) * 3;
        
        // Wet/dry mix
        h.dryGain.gain.value = 1;
        h.wetGain.gain.value = s.enabled ? 1 : 0;
    }
    
    /**
     * Update spatial audio settings
     */
    setSpatial(options) {
        Object.assign(this.settings.spatial, options);
        this._updateSpatial();
        this._emit('spatialChanged', this.settings.spatial);
    }
    
    _updateSpatial() {
        const sp = this.modules.spatial;
        const s = this.settings.spatial;
        
        if (!sp || !this.isInitialized) return;
        
        // Stereo width - adjust side gain
        const width = s.width || 1.0;
        sp.sideGain.gain.value = width;
        
        // Slight L/R balance adjustment for width
        sp.leftGain.gain.value = 1 + (width - 1) * 0.1;
        sp.rightGain.gain.value = 1 + (width - 1) * 0.1;
        
        // Depth - delay amount
        const depth = s.depth || 0.5;
        sp.delayL.delayTime.value = 0.005 + depth * 0.015;
        sp.delayR.delayTime.value = 0.007 + depth * 0.018;
        sp.delayGain.gain.value = depth * 0.15;
        
        // Room reverb amount
        const roomAmounts = {
            'studio': 0.1,
            'analog': 0.15,
            'concert': 0.3,
            'club': 0.2,
            'theater': 0.25,
            'open': 0.05
        };
        const roomAmount = roomAmounts[s.room] || 0.1;
        sp.convolverGain.gain.value = s.enabled ? roomAmount : 0;
        sp.dryGain.gain.value = 1 - (roomAmount * 0.3);
        
        // Apply room impulse if available
        if (this.roomImpulses && this.roomImpulses[s.room]) {
            sp.convolver.buffer = this.roomImpulses[s.room];
        }
    }
    
    /**
     * Update dynamics processor settings
     */
    setDynamics(options) {
        Object.assign(this.settings.dynamics, options);
        this._updateDynamics();
        this._emit('dynamicsChanged', this.settings.dynamics);
    }
    
    _updateDynamics() {
        const d = this.modules.dynamics;
        const s = this.settings.dynamics;
        
        if (!d || !this.isInitialized) return;
        
        // Mode presets
        const modes = {
            'pure': { threshold: -50, ratio: 1, makeup: 1 },
            'enhanced': { threshold: -24, ratio: 2, makeup: 1.1 },
            'balanced': { threshold: -18, ratio: 3, makeup: 1.05 },
            'night': { threshold: -12, ratio: 6, makeup: 0.9 },
            'compressed': { threshold: -8, ratio: 8, makeup: 0.85 }
        };
        
        const mode = modes[s.mode] || modes['balanced'];
        
        d.compressor.threshold.value = mode.threshold;
        d.compressor.ratio.value = mode.ratio;
        d.makeupGain.gain.value = mode.makeup;
        
        // Attack and release
        d.compressor.attack.value = (s.attack || 10) / 1000;
        d.compressor.release.value = (s.release || 100) / 1000;
        
        // Limiter ceiling
        d.limiter.threshold.value = s.ceiling || -1;
        
        // Enable/disable
        if (!s.enabled) {
            d.compressor.ratio.value = 1;
            d.makeupGain.gain.value = 1;
        }
    }
    
    /**
     * Update acoustic color settings
     */
    setColor(options) {
        Object.assign(this.settings.color, options);
        this._updateColor();
        this._emit('colorChanged', this.settings.color);
    }
    
    _updateColor() {
        const c = this.modules.color;
        const s = this.settings.color;
        
        if (!c || !this.isInitialized) return;
        
        // Body (low mids) - 0.5 is neutral
        c.lowBand.gain.value = (s.body - 0.5) * 8;
        
        // Warmth (mids warmth)
        c.lowMidBand.gain.value = (s.warmth - 0.5) * 6;
        
        // Brightness (high mids)
        c.highMidBand.gain.value = (s.brightness - 0.5) * 6;
        
        // Air (highs)
        c.highBand.gain.value = (s.air - 0.5) * 8;
        
        // Punch (presence + transients)
        c.midBand.gain.value = (s.punch - 0.5) * 4;
        
        // Saturation based on warmth
        const satAmount = Math.max(0, (s.warmth - 0.4) * 0.5);
        c.saturator.curve = this._makeSaturationCurve(satAmount);
        c.saturatorGain.gain.value = satAmount * 0.3;
        
        c.output.gain.value = s.enabled ? 1 : 1;
    }
    
    /**
     * Set master volume
     */
    setVolume(value) {
        this.settings.output.volume = Math.max(0, Math.min(1, value));
        if (this.modules.master) {
            this.modules.master.gain.gain.value = this.settings.output.volume;
        }
    }
    
    /**
     * Enable/disable the engine
     */
    setEnabled(enabled) {
        this.isEnabled = enabled;
        
        if (!this.isInitialized) return;
        
        if (enabled && !this.isBypassed) {
            this._updateHarmonic();
            this._updateSpatial();
            this._updateDynamics();
            this._updateColor();
        } else {
            // Bypass all processing - set to unity/passthrough
            this.modules.harmonic.wetGain.gain.value = 1;
            this.modules.harmonic.dryGain.gain.value = 1;
            this.modules.harmonic.lowShelf.gain.value = 0;
            this.modules.harmonic.highShelf.gain.value = 0;
            this.modules.harmonic.presencePeak.gain.value = 0;
            this.modules.harmonic.transientGain.gain.value = 0;
            this.modules.harmonic.subBassGain.gain.value = 0;
            this.modules.harmonic.airGain.gain.value = 0;
            this.modules.spatial.convolverGain.gain.value = 0;
            this.modules.spatial.delayGain.gain.value = 0;
            this.modules.spatial.dryGain.gain.value = 1;
            this.modules.dynamics.compressor.ratio.value = 1;
            this.modules.dynamics.makeupGain.gain.value = 1;
            this.modules.color.lowBand.gain.value = 0;
            this.modules.color.lowMidBand.gain.value = 0;
            this.modules.color.midBand.gain.value = 0;
            this.modules.color.highMidBand.gain.value = 0;
            this.modules.color.highBand.gain.value = 0;
            this.modules.color.saturatorGain.gain.value = 0;
        }
        
        this._emit('enabledChanged', enabled);
    }
    
    /**
     * Set bypass mode (direct audio output, no processing)
     */
    setBypass(bypass) {
        this.isBypassed = bypass;
        if (this.isInitialized) {
            this._connectGraph();
        }
        console.log(`🎵 Wave Engine bypass: ${bypass}`);
    }
    
    /**
     * Get visualization data
     */
    getVisualizationData() {
        if (!this.isInitialized) return this.visualData;
        
        const analyser = this.modules.visualizer.analyser;
        const masterAnalyser = this.modules.master.analyser;
        
        // Spectrum data
        const freqData = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(freqData);
        for (let i = 0; i < Math.min(256, freqData.length); i++) {
            this.visualData.spectrum[i] = freqData[i] / 255;
        }
        
        // Waveform data
        const timeData = new Uint8Array(analyser.fftSize);
        analyser.getByteTimeDomainData(timeData);
        for (let i = 0; i < Math.min(256, timeData.length); i++) {
            this.visualData.waveform[i] = (timeData[i] - 128) / 128;
        }
        
        // Loudness (RMS)
        let sum = 0;
        for (let i = 0; i < timeData.length; i++) {
            const val = (timeData[i] - 128) / 128;
            sum += val * val;
        }
        this.visualData.loudness = Math.sqrt(sum / timeData.length);
        
        // Peak
        const masterData = new Uint8Array(masterAnalyser.frequencyBinCount);
        masterAnalyser.getByteFrequencyData(masterData);
        this.visualData.peak = Math.max(...masterData) / 255;
        
        return this.visualData;
    }
    
    /**
     * Get current settings
     */
    getSettings() {
        return JSON.parse(JSON.stringify(this.settings));
    }
    
    /**
     * Load settings
     */
    loadSettings(settings) {
        if (settings.harmonic) this.setHarmonic(settings.harmonic);
        if (settings.spatial) this.setSpatial(settings.spatial);
        if (settings.dynamics) this.setDynamics(settings.dynamics);
        if (settings.color) this.setColor(settings.color);
        if (settings.output) this.setVolume(settings.output.volume);
    }
    
    /**
     * Resume audio context (required after user interaction)
     */
    async resume() {
        if (this.audioContext && this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
            console.log('🎵 Audio context resumed');
        }
    }
    
    /**
     * Event handling
     */
    on(event, callback) {
        if (!this.callbacks[event]) {
            this.callbacks[event] = [];
        }
        this.callbacks[event].push(callback);
    }
    
    off(event, callback) {
        if (this.callbacks[event]) {
            this.callbacks[event] = this.callbacks[event].filter(cb => cb !== callback);
        }
    }
    
    _emit(event, data) {
        if (this.callbacks[event]) {
            this.callbacks[event].forEach(cb => cb(data));
        }
    }
    
    /**
     * Cleanup
     */
    destroy() {
        if (this.audioContext) {
            this.audioContext.close();
        }
        this.isInitialized = false;
        this.callbacks = {};
    }
}

// Export for use
window.WaveEngine = WaveEngine;

console.log('🎵 Musify Wave Engine loaded');
