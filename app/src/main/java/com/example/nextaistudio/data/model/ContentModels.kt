package com.example.nextaistudio.data.model

data class Beat(
    val t: String,
    val tags: List<String> = emptyList()
)

data class ContentEntry(
    val id: String,
    val kind: String = "long", // "long" or "short"
    val title: String,
    val description: String,
    val tags: List<String> = emptyList(),
    val categoryId: String = "28", // Science & Technology
    val madeForKids: Boolean = false,
    val seed: Long = 42L,
    val narration: String,
    val beats: List<Beat> = emptyList(),
    val contentPillar: String = "ai_updates", // "ai_updates", "gadget_reviews", "personal_finance"
    val contentPolicyVersion: String = "2026-10-01",
    val scopeReviewed: Boolean = true,
    val verifiedSources: List<String> = emptyList(),
    val demandEvidence: String = "",
    val recycledFrom: String? = null
) {
    val wordCount: Int
        get() = narration.split("\\s+".toRegex()).count { it.isNotBlank() }

    val estimatedDurationSeconds: Int
        get() = (wordCount / 2.3).toInt() // Kokoro documentary rate ~138 wpm

    val isShort: Boolean
        get() = kind.equals("short", ignoreCase = true)
}

data class PublishedVideo(
    val id: String,
    val videoId: String,
    val title: String,
    val kind: String, // "long" or "short"
    val uploadedAt: String,
    val scheduledFor: String?,
    val url: String
)

data class RunResult(
    val id: String,
    val date: String,
    val status: String, // "scheduled", "published", "rendered"
    val file: String,
    val videoId: String,
    val scheduledFor: String,
    val url: String,
    val thumbnailStatus: String = "completed",
    val thumbnailSource: String = "ChatGPT DALL-E / Compose Studio",
    val polished: Boolean = false,
    val commentStatus: String = "paused_budget_rules",
    val thumbPrompt: String = ""
)

data class ScheduleSlot(
    val timeLabel: String,
    val kind: String,
    val dateString: String,
    val utcTimestamp: String,
    val gapHours: Double,
    val isEligible: Boolean,
    val statusText: String
)

data class FootageClip(
    val file: String,
    val category: String,
    val duration: Double,
    val width: Int,
    val height: Int,
    val sourceUrl: String = ""
)

data class WorkflowTemplate(
    val id: String,
    val name: String,
    val description: String,
    val cron: String,
    val triggerDhakaTime: String,
    val targetFormat: String,
    val isActive: Boolean,
    val guardRules: List<String>
)

enum class CheckStatus {
    PASSED,
    WARNING,
    FAILED
}

data class PreflightCheck(
    val id: String,
    val name: String,
    val category: String,
    val status: CheckStatus,
    val message: String,
    val detail: String
)
