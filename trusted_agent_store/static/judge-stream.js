/**
 * SSE Client for Collaborative Jury Judge Real-time Updates
 *
 * 受信したイベントは WebSocket 時代のハンドラ互換で emit する。
 */

class JuryJudgeStream {
    constructor(submissionId, options = {}) {
        this.submissionId = submissionId;
        this.options = {
            reconnectInterval: 3000,
            maxReconnectAttempts: 10,
            basePath: "", // e.g., "/store" for Cloud Run prefix
            ...options
        };

        this.es = null;
        this.isConnected = false;
        this.eventHandlers = {};

        // Status tracking
        this.currentPhase = null;
        this.currentRound = 0;
        this.jurorEvaluations = {};
    }

    /**
     * Connect via Server-Sent Events
     */
    connect() {
        const base = window.location.origin.replace(/\/$/, '');
        const prefix = this.options.basePath ? this.options.basePath.replace(/\/$/, '') : "";
        const esUrl = `${base}${prefix}/sse/submissions/${this.submissionId}/judge`;

        console.log(`[JuryJudgeSSE] 🔌 Connecting to ${esUrl}`);

        try {
            this.es = new EventSource(esUrl, { withCredentials: false });

            this.es.onopen = () => {
                this.isConnected = true;
                this.emit('connected');
                console.log('[JuryJudgeSSE] 🟢 Connected');
            };

            this.es.onmessage = (event) => {
                if (!event?.data) return;
                this.handleMessage(event);
            };

            this.es.addEventListener('ping', () => {
                // heartbeat no-op
            });

            this.es.onerror = (error) => {
                console.error('[JuryJudgeSSE] ❌ SSE error:', error);
                this.isConnected = false;
                this.emit('connection_error', error);
                // EventSourceは自動再接続するので手動は不要
            };
        } catch (error) {
            console.error('[JuryJudgeSSE] ❌ Connection init error:', error);
        }
    }

    /**
     * Handle incoming SSE message
     */
    handleMessage(event) {
        console.log('[JuryJudgeSSE] 📨 Raw message received:', event.data);

        try {
            const data = JSON.parse(event.data);
            console.log('[JuryJudgeSSE] 📦 Parsed message data:', data);

            const { type } = data;

            switch (type) {
                case 'evaluation_started':
                case 'phase_started':
                case 'phase_change':
                    this.handlePhaseChange(data);
                    break;
                case 'juror_evaluation':
                    this.handleJurorEvaluation(data);
                    break;
                case 'consensus_check':
                    this.handleConsensusCheck(data);
                    break;
                case 'round_started':
                case 'discussion_start':
                    this.handleDiscussionStart(data);
                    break;
                case 'juror_statement':
                    this.handleJurorStatement(data);
                    break;
                case 'round_completed':
                case 'round_complete':
                    this.handleRoundComplete(data);
                    break;
                case 'final_judge_chunk':
                    this.emit('final_judge_chunk', { chunk: data.chunk });
                    break;
                case 'final_judgment':
                case 'evaluation_completed':
                    this.handleFinalJudgment(data);
                    break;
                case 'stage_update':
                    this.emit('stage_update', data);
                    break;
                case 'score_update':
                    this.emit('score_update', data);
                    break;
                case 'submission_state_change':
                    this.emit('submission_state_change', data);
                    break;
                case 'initial_state':
                    this.emit('initial_state', data);
                    break;
                case 'error':
                    this.handleBackendError(data);
                    break;
                // PreCheck events
                case 'precheck_started':
                    this.emit('precheck_started', data);
                    break;
                case 'precheck_completed':
                    this.emit('precheck_completed', data);
                    break;
                // Security Gate events
                case 'security_started':
                    this.emit('security_started', data);
                    break;
                case 'security_test_started':
                    this.emit('security_test_started', data);
                    break;
                case 'security_scenario_result':
                    this.emit('security_scenario_result', data);
                    break;
                case 'security_completed':
                    this.emit('security_completed', data);
                    break;
                // Agent Card Accuracy (Functional) events
                case 'functional_started':
                    this.emit('functional_started', data);
                    break;
                case 'functional_scenario_result':
                    this.emit('functional_scenario_result', data);
                    break;
                case 'functional_turn_progress':
                    this.emit('functional_turn_progress', data);
                    break;
                case 'functional_completed':
                    this.emit('functional_completed', data);
                    break;
                default:
                    this.emit('message', data);
            }

        } catch (error) {
            console.error('[JuryJudgeSSE] ❌ Message parsing error:', error);
        }
    }

    /**
     * Handle phase change (Phase 1: Independent, Phase 2: Discussion, Phase 3: Final)
     */
    handlePhaseChange(data) {
        console.log('[JuryJudgeWS] 🔄 Phase change:', data);
        this.currentPhase = data.phase;
        this.emit('phase_change', {
            phase: data.phase,
            phaseNumber: data.phaseNumber,
            description: data.description
        });
        console.log(`[JuryJudgeWS] 🔄 Emitted phase_change event: Phase ${data.phaseNumber} - ${data.phase}`);
    }

    /**
     * Handle individual juror evaluation
     */
    handleJurorEvaluation(data) {
        const { juror, phase, verdict, score, confidence, rationale,
                taskCompletion, toolUsage, autonomy, safety } = data;

        if (!this.jurorEvaluations[juror]) {
            this.jurorEvaluations[juror] = {};
        }

        this.jurorEvaluations[juror][phase] = {
            verdict,
            score,
            confidence,
            rationale,
            // AISI 4軸スコア
            taskCompletion,
            toolUsage,
            autonomy,
            safety,
            timestamp: new Date()
        };

        this.emit('juror_evaluation', {
            juror,
            phase,
            verdict,
            score,
            confidence,
            rationale,
            // AISI 4軸スコア
            taskCompletion,
            toolUsage,
            autonomy,
            safety
        });
    }

    /**
     * Handle consensus check result
     */
    handleConsensusCheck(data) {
        this.emit('consensus_check', {
            consensusStatus: data.consensusStatus,
            consensusReached: data.consensusReached,
            consensusVerdict: data.consensusVerdict,
            round: data.round
        });
    }

    /**
     * Handle discussion start
     */
    handleDiscussionStart(data) {
        this.currentRound = data.round;
        this.emit('discussion_start', {
            round: data.round,
            speakerOrder: data.speakerOrder
        });
    }

    /**
     * Handle juror statement in discussion
     */
    handleJurorStatement(data) {
        this.emit('juror_statement', {
            round: data.round,
            juror: data.juror,
            statement: data.statement,
            positionChanged: data.positionChanged,
            newVerdict: data.newVerdict,
            newScore: data.newScore
        });
    }

    /**
     * Handle round completion
     */
    handleRoundComplete(data) {
        this.emit('round_complete', {
            round: data.round,
            consensusReached: data.consensusReached,
            stagnant: data.stagnant
        });
    }

    /**
     * Handle final judgment
     */
    handleFinalJudgment(data) {
        this.emit('final_judgment', {
            method: data.method,
            finalVerdict: data.finalVerdict,
            finalScore: data.finalScore,
            confidence: data.confidence,
            rationale: data.rationale,
            scoreBreakdown: data.scoreBreakdown
        });

        // Evaluation complete
        this.emit('evaluation_complete', data);
    }

    /**
     * Handle backend error
     */
    handleBackendError(data) {
        console.error('[JuryJudgeWS] Backend error:', data.message);
        this.emit('error', {
            message: data.message,
            details: data.details
        });
    }

    /**
     * Handle WebSocket error
     */
    /**
     * Register event handler
     */
    on(event, handler) {
        if (!this.eventHandlers[event]) {
            this.eventHandlers[event] = [];
        }
        this.eventHandlers[event].push(handler);
    }

    /**
     * Unregister event handler
     */
    off(event, handler) {
        if (this.eventHandlers[event]) {
            this.eventHandlers[event] = this.eventHandlers[event].filter(h => h !== handler);
        }
    }

    /**
     * Emit event to all registered handlers
     */
    emit(event, data) {
        console.log(`[JuryJudgeWS] 📡 Emitting event: "${event}"`, data);
        if (this.eventHandlers[event]) {
            console.log(`[JuryJudgeWS] 📡 ${this.eventHandlers[event].length} handler(s) registered for "${event}"`);
            this.eventHandlers[event].forEach((handler, index) => {
                try {
                    console.log(`[JuryJudgeWS] 📡 Calling handler ${index + 1} for "${event}"`);
                    handler(data);
                    console.log(`[JuryJudgeWS] ✅ Handler ${index + 1} for "${event}" completed successfully`);
                } catch (error) {
                    console.error(`[JuryJudgeWS] ❌ Error in event handler ${index + 1} for '${event}':`, error);
                }
            });
        } else {
            console.warn(`[JuryJudgeWS] ⚠️ No handlers registered for event "${event}"`);
        }
    }

    /**
     * Disconnect from WebSocket
     */
    disconnect() {
        console.log('[JuryJudgeSSE] Disconnecting');
        if (this.es) {
            this.es.close();
            this.es = null;
        }
        this.isConnected = false;
    }

    /**
     * Get current status
     */
    getStatus() {
        return {
            connected: this.isConnected,
            phase: this.currentPhase,
            round: this.currentRound,
            jurorEvaluations: this.jurorEvaluations
        };
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = JuryJudgeStream;
}
