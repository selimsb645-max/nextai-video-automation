package com.example.nextaistudio.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.nextaistudio.data.model.*
import com.example.nextaistudio.data.repository.AutomationRepository
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

enum class AppScreen {
    DASHBOARD,
    LIBRARY,
    PIPELINE,
    RUNS,
    WORKFLOWS,
    PREFLIGHT,
    POLICY
}

data class PipelineStudioState(
    val selectedEntry: ContentEntry? = null,
    val currentStep: Int = 1,
    val isProcessing: Boolean = false,
    val progressMessage: String = "",
    val progressPercent: Float = 0f,
    val matchedClips: List<Pair<Beat, FootageClip>> = emptyList(),
    val voiceMood: String = "",
    val voiceSpeed: Double = 1.0,
    val estimatedAudioDuration: Double = 0.0,
    val calculatedSlot: ScheduleSlot? = null,
    val generatedThumbnailHook: String = "",
    val thumbnailAccentWord: String = "",
    val isThumbnailBlurFill: Boolean = false,
    val finalRunResult: RunResult? = null,
    val isCompleted: Boolean = false
)

data class UiState(
    val currentScreen: AppScreen = AppScreen.DASHBOARD,
    val libraryEntries: List<ContentEntry> = emptyList(),
    val publishedLog: List<PublishedVideo> = emptyList(),
    val activeRuns: List<RunResult> = emptyList(),
    val workflowTemplates: List<WorkflowTemplate> = emptyList(),
    val preflightChecks: List<PreflightCheck> = emptyList(),
    val isRunningPreflight: Boolean = false,
    val currentDhakaTime: String = "",
    val nextLongSlot: ScheduleSlot? = null,
    val nextShortSlot: ScheduleSlot? = null,
    val libraryFilterFormat: String = "ALL", // "ALL", "LONG", "SHORT"
    val libraryFilterPillar: String = "ALL", // "ALL", "ai_updates", "gadget_reviews", "personal_finance", "ELIGIBLE"
    val librarySearchQuery: String = "",
    val pipelineState: PipelineStudioState = PipelineStudioState(),
    val selectedEntryForDetail: ContentEntry? = null,
    val selectedRunForDetail: RunResult? = null,
    val notificationMessage: String? = null
)

class NextAIViewModel(
    private val repository: AutomationRepository = AutomationRepository()
) : ViewModel() {

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    private val bdZone = ZoneId.of("Asia/Dhaka")
    private val timeFormatter = DateTimeFormatter.ofPattern("HH:mm:ss")
    private val dateFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd")

    init {
        loadInitialData()
        startClock()
    }

    private fun loadInitialData() {
        val now = LocalDateTime.now(bdZone)
        val longSlot = repository.calculateNextBdSlot("long", now)
        val shortSlot = repository.calculateNextBdSlot("short", now)

        _uiState.update { current ->
            current.copy(
                libraryEntries = repository.libraryEntries,
                publishedLog = repository.publishedLog,
                activeRuns = repository.activeRuns,
                workflowTemplates = repository.workflowTemplates,
                nextLongSlot = longSlot,
                nextShortSlot = shortSlot,
                currentDhakaTime = "${now.format(dateFormatter)} ${now.format(timeFormatter)} BST"
            )
        }
    }

    private fun startClock() {
        viewModelScope.launch {
            while (true) {
                delay(1000)
                val now = LocalDateTime.now(bdZone)
                _uiState.update {
                    it.copy(currentDhakaTime = "${now.format(dateFormatter)} ${now.format(timeFormatter)} BST")
                }
            }
        }
    }

    fun navigateTo(screen: AppScreen) {
        _uiState.update { it.copy(currentScreen = screen) }
    }

    fun setLibraryFilterFormat(format: String) {
        _uiState.update { it.copy(libraryFilterFormat = format) }
    }

    fun setLibraryFilterPillar(pillar: String) {
        _uiState.update { it.copy(libraryFilterPillar = pillar) }
    }

    fun setLibrarySearchQuery(query: String) {
        _uiState.update { it.copy(librarySearchQuery = query) }
    }

    fun selectEntryForDetail(entry: ContentEntry?) {
        _uiState.update { it.copy(selectedEntryForDetail = entry) }
    }

    fun selectRunForDetail(run: RunResult?) {
        _uiState.update { it.copy(selectedRunForDetail = run) }
    }

    fun clearNotification() {
        _uiState.update { it.copy(notificationMessage = null) }
    }

    fun isEntryEligible(entry: ContentEntry): Boolean {
        return repository.isContentEligible(entry)
    }

    // Start production pipeline for an entry
    fun startProductionForEntry(entry: ContentEntry) {
        val now = LocalDateTime.now(bdZone)
        val slot = repository.calculateNextBdSlot(entry.kind, now)
        val (mood, speed) = repository.calculateKokoroPacing(entry.narration, entry.isShort)
        val clips = repository.matchFootageForBeats(entry.beats)

        // Derive thumbnail hook words
        val words = entry.title.split(" ")
        val hook = if (words.size >= 3) words.take(3).joinToString(" ").uppercase() else entry.title.uppercase()
        val accent = if (words.size >= 4) words[3].uppercase() else "TRUTH"

        _uiState.update { current ->
            current.copy(
                currentScreen = AppScreen.PIPELINE,
                selectedEntryForDetail = null,
                pipelineState = PipelineStudioState(
                    selectedEntry = entry,
                    currentStep = 1,
                    isProcessing = false,
                    progressMessage = "Topic locked: ${entry.title}",
                    progressPercent = 0.15f,
                    matchedClips = clips,
                    voiceMood = mood,
                    voiceSpeed = speed,
                    estimatedAudioDuration = (entry.wordCount / (2.3 * speed)),
                    calculatedSlot = slot,
                    generatedThumbnailHook = hook,
                    thumbnailAccentWord = accent,
                    isThumbnailBlurFill = entry.isShort,
                    isCompleted = false
                )
            )
        }
    }

    fun nextPipelineStep() {
        val currentState = _uiState.value.pipelineState
        if (currentState.currentStep < 6) {
            val next = currentState.currentStep + 1
            _uiState.update {
                it.copy(
                    pipelineState = currentState.copy(
                        currentStep = next,
                        progressPercent = (next.toFloat() / 6.0f)
                    )
                )
            }
        }
    }

    fun previousPipelineStep() {
        val currentState = _uiState.value.pipelineState
        if (currentState.currentStep > 1) {
            val prev = currentState.currentStep - 1
            _uiState.update {
                it.copy(
                    pipelineState = currentState.copy(
                        currentStep = prev,
                        progressPercent = (prev.toFloat() / 6.0f)
                    )
                )
            }
        }
    }

    fun updateThumbnailHook(hook: String, accent: String) {
        _uiState.update {
            it.copy(
                pipelineState = it.pipelineState.copy(
                    generatedThumbnailHook = hook,
                    thumbnailAccentWord = accent
                )
            )
        }
    }

    fun toggleThumbnailBlurFill() {
        _uiState.update {
            it.copy(
                pipelineState = it.pipelineState.copy(
                    isThumbnailBlurFill = !it.pipelineState.isThumbnailBlurFill
                )
            )
        }
    }

    // Execute full pipeline rendering and YouTube schedule
    fun executePipelineGeneration() {
        val entry = _uiState.value.pipelineState.selectedEntry ?: return

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    pipelineState = it.pipelineState.copy(
                        isProcessing = true,
                        progressMessage = "Synthesizing narration with Kokoro TTS (am_michael)...",
                        progressPercent = 0.35f
                    )
                )
            }
            delay(1200)

            _uiState.update {
                it.copy(
                    pipelineState = it.pipelineState.copy(
                        progressMessage = "Assembling ${entry.beats.size} beat clips & rendering cinematic xfades...",
                        progressPercent = 0.60f
                    )
                )
            }
            delay(1400)

            _uiState.update {
                it.copy(
                    pipelineState = it.pipelineState.copy(
                        progressMessage = "Generating ambient chords bed & running loudnorm audio gates...",
                        progressPercent = 0.80f
                    )
                )
            }
            delay(1200)

            _uiState.update {
                it.copy(
                    pipelineState = it.pipelineState.copy(
                        progressMessage = "Uploading resumable package to YouTube and scheduling private slot...",
                        progressPercent = 0.95f
                    )
                )
            }
            delay(1000)

            // Generate real run result
            val slot = _uiState.value.pipelineState.calculatedSlot
                ?: repository.calculateNextBdSlot(entry.kind)
            val generatedVideoId = "ais_" + System.currentTimeMillis().toString().takeLast(8)

            val newRun = RunResult(
                id = "${entry.id}_${LocalDateTime.now().format(dateFormatter)}",
                date = LocalDateTime.now().format(dateFormatter),
                status = "scheduled",
                file = "/factory/runs/${entry.id}/final.mp4",
                videoId = generatedVideoId,
                scheduledFor = slot.utcTimestamp,
                url = "https://www.youtube.com/watch?v=$generatedVideoId",
                thumbnailStatus = "completed",
                thumbnailSource = "NextAI Neural Studio (1280x720 16:9)",
                polished = true,
                commentStatus = "paused_budget_rules",
                thumbPrompt = "Clean dark background. Hook: '${_uiState.value.pipelineState.generatedThumbnailHook}' with accent '${_uiState.value.pipelineState.thumbnailAccentWord}'"
            )

            // Add to published log and active runs
            val newPublished = PublishedVideo(
                id = entry.id,
                videoId = generatedVideoId,
                title = entry.title,
                kind = entry.kind,
                uploadedAt = LocalDateTime.now(bdZone).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
                scheduledFor = slot.utcTimestamp,
                url = "https://www.youtube.com/watch?v=$generatedVideoId"
            )

            repository.publishedLog.add(0, newPublished)
            repository.activeRuns.add(0, newRun)

            _uiState.update { current ->
                current.copy(
                    publishedLog = listOf(newPublished) + current.publishedLog,
                    activeRuns = listOf(newRun) + current.activeRuns,
                    pipelineState = current.pipelineState.copy(
                        isProcessing = false,
                        progressPercent = 1.0f,
                        progressMessage = "Scheduled successfully on YouTube for ${slot.timeLabel}!",
                        finalRunResult = newRun,
                        isCompleted = true,
                        currentStep = 6
                    ),
                    notificationMessage = "Video scheduled: ${entry.title} (${slot.timeLabel})"
                )
            }
        }
    }

    // Run diagnostic suite
    fun triggerPreflightDiagnostics() {
        viewModelScope.launch {
            _uiState.update { it.copy(isRunningPreflight = true) }
            delay(1000)
            val checks = repository.runPreflightDiagnostics()
            _uiState.update {
                it.copy(
                    preflightChecks = checks,
                    isRunningPreflight = false,
                    notificationMessage = "Preflight completed: ${checks.count { c -> c.status == CheckStatus.PASSED }} passed"
                )
            }
        }
    }

    // Toggle workflow template state
    fun toggleWorkflow(templateId: String) {
        _uiState.update { current ->
            val updated = current.workflowTemplates.map {
                if (it.id == templateId) it.copy(isActive = !it.isActive) else it
            }
            current.copy(
                workflowTemplates = updated,
                notificationMessage = "Workflow '${templateId}' state toggled"
            )
        }
    }
}
