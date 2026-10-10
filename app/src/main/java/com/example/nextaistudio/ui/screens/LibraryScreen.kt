package com.example.nextaistudio.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.example.nextaistudio.data.model.ContentEntry
import com.example.nextaistudio.ui.theme.*
import com.example.nextaistudio.ui.viewmodel.UiState

@Composable
fun LibraryScreen(
    state: UiState,
    onFilterFormat: (String) -> Unit,
    onFilterPillar: (String) -> Unit,
    onSearchQuery: (String) -> Unit,
    onSelectEntry: (ContentEntry?) -> Unit,
    onStartProduction: (ContentEntry) -> Unit,
    isEntryEligible: (ContentEntry) -> Boolean
) {
    val filteredEntries = state.libraryEntries.filter { entry ->
        val matchesFormat = when (state.libraryFilterFormat) {
            "LONG" -> !entry.isShort
            "SHORT" -> entry.isShort
            else -> true
        }
        val matchesPillar = when (state.libraryFilterPillar) {
            "ai_updates" -> entry.contentPillar == "ai_updates"
            "gadget_reviews" -> entry.contentPillar == "gadget_reviews"
            "personal_finance" -> entry.contentPillar == "personal_finance"
            "ELIGIBLE" -> isEntryEligible(entry)
            else -> true
        }
        val matchesQuery = state.librarySearchQuery.isBlank() ||
                entry.title.contains(state.librarySearchQuery, ignoreCase = true) ||
                entry.description.contains(state.librarySearchQuery, ignoreCase = true) ||
                entry.tags.any { it.contains(state.librarySearchQuery, ignoreCase = true) }

        matchesFormat && matchesPillar && matchesQuery
    }

    Box(modifier = Modifier.fillMaxSize().background(StudioDarkBackground)) {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp),
            contentPadding = PaddingValues(top = 16.dp, bottom = 96.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header & Search
            item {
                Column {
                    Text(
                        text = "Content Library",
                        style = MaterialTheme.typography.headlineMedium,
                        color = TextPrimary,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "Verified topics, beat breakdowns & SEO scripts",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary
                    )
                    Spacer(modifier = Modifier.height(14.dp))

                    OutlinedTextField(
                        value = state.librarySearchQuery,
                        onValueChange = onSearchQuery,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("library_search_input"),
                        placeholder = { Text("Search topics, tags, platforms...", color = TextMuted) },
                        leadingIcon = {
                            Icon(Icons.Default.Search, contentDescription = "Search", tint = TextSecondary)
                        },
                        trailingIcon = {
                            if (state.librarySearchQuery.isNotEmpty()) {
                                IconButton(onClick = { onSearchQuery("") }) {
                                    Icon(Icons.Default.Close, contentDescription = "Clear", tint = TextSecondary)
                                }
                            }
                        },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedContainerColor = StudioSurfaceDark,
                            unfocusedContainerColor = StudioSurfaceDark,
                            focusedBorderColor = StudioPrimary,
                            unfocusedBorderColor = BorderSubtle,
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary
                        ),
                        shape = RoundedCornerShape(12.dp),
                        singleLine = true
                    )
                }
            }

            // Format Filter Chips
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilterChip(
                        selected = state.libraryFilterFormat == "ALL",
                        onClick = { onFilterFormat("ALL") },
                        label = { Text("All Formats") },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = StudioPrimary,
                            selectedLabelColor = Color.Black
                        )
                    )
                    FilterChip(
                        selected = state.libraryFilterFormat == "LONG",
                        onClick = { onFilterFormat("LONG") },
                        label = { Text("Longs (16:9)") },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = StudioPrimary,
                            selectedLabelColor = Color.Black
                        )
                    )
                    FilterChip(
                        selected = state.libraryFilterFormat == "SHORT",
                        onClick = { onFilterFormat("SHORT") },
                        label = { Text("Shorts (9:16)") },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = StudioPrimary,
                            selectedLabelColor = Color.Black
                        )
                    )
                }
            }

            // Pillar Filter Row
            item {
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    item {
                        FilterChip(
                            selected = state.libraryFilterPillar == "ALL",
                            onClick = { onFilterPillar("ALL") },
                            label = { Text("All Pillars") }
                        )
                    }
                    item {
                        FilterChip(
                            selected = state.libraryFilterPillar == "ELIGIBLE",
                            onClick = { onFilterPillar("ELIGIBLE") },
                            label = { Text("Eligible Only") },
                            leadingIcon = {
                                Box(
                                    modifier = Modifier
                                        .size(6.dp)
                                        .clip(CircleShape)
                                        .background(StudioAccentGreen)
                                )
                            }
                        )
                    }
                    item {
                        FilterChip(
                            selected = state.libraryFilterPillar == "ai_updates",
                            onClick = { onFilterPillar("ai_updates") },
                            label = { Text("AI Updates") }
                        )
                    }
                    item {
                        FilterChip(
                            selected = state.libraryFilterPillar == "gadget_reviews",
                            onClick = { onFilterPillar("gadget_reviews") },
                            label = { Text("Gadget Reviews") }
                        )
                    }
                    item {
                        FilterChip(
                            selected = state.libraryFilterPillar == "personal_finance",
                            onClick = { onFilterPillar("personal_finance") },
                            label = { Text("Personal Finance") }
                        )
                    }
                }
            }

            // Results count
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "${filteredEntries.size} topics found",
                        fontSize = 12.sp,
                        color = TextMuted
                    )
                    Text(
                        text = "Policy: Asia/Dhaka Schedule",
                        fontSize = 11.sp,
                        color = TextMuted
                    )
                }
            }

            // Entries List
            items(filteredEntries, key = { it.id }) { entry ->
                val eligible = isEntryEligible(entry)
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onSelectEntry(entry) }
                        .testTag("entry_card_${entry.id}"),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                    border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.Top
                        ) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // Format Badge
                                Box(
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(6.dp))
                                        .background(if (entry.isShort) StudioSecondary.copy(alpha = 0.2f) else StudioPrimary.copy(alpha = 0.2f))
                                        .padding(horizontal = 8.dp, vertical = 3.dp)
                                ) {
                                    Text(
                                        text = if (entry.isShort) "SHORT 9:16" else "LONG 16:9",
                                        fontSize = 10.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = if (entry.isShort) StudioSecondary else StudioPrimary
                                    )
                                }

                                // Pillar Badge
                                Box(
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(6.dp))
                                        .background(StudioSurfaceCard)
                                        .padding(horizontal = 8.dp, vertical = 3.dp)
                                ) {
                                    Text(
                                        text = entry.contentPillar.replace("_", " ").uppercase(),
                                        fontSize = 10.sp,
                                        color = TextSecondary
                                    )
                                }
                            }

                            // Eligibility Indicator
                            Box(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(if (eligible) StudioAccentGreen.copy(alpha = 0.15f) else StudioAccentRed.copy(alpha = 0.15f))
                                    .padding(horizontal = 8.dp, vertical = 3.dp)
                            ) {
                                Text(
                                    text = if (eligible) "ELIGIBLE" else "OUT OF SCOPE",
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = if (eligible) StudioAccentGreen else StudioAccentRed
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(10.dp))

                        Text(
                            text = entry.title,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )

                        Spacer(modifier = Modifier.height(6.dp))

                        Text(
                            text = entry.description,
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondary,
                            maxLines = 2
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        // Stats & Action Bar
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text(
                                    text = "${entry.wordCount} words",
                                    fontSize = 11.sp,
                                    color = TextMuted
                                )
                                Text(
                                    text = "~${entry.estimatedDurationSeconds}s",
                                    fontSize = 11.sp,
                                    color = TextMuted
                                )
                                Text(
                                    text = "${entry.beats.size} beats",
                                    fontSize = 11.sp,
                                    color = TextMuted
                                )
                            }

                            if (eligible) {
                                Button(
                                    onClick = { onStartProduction(entry) },
                                    shape = RoundedCornerShape(8.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = StudioPrimary),
                                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.PlayArrow,
                                        contentDescription = null,
                                        tint = Color.Black,
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text("Produce", fontSize = 12.sp, color = Color.Black, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                }
            }
        }

        // Entry Detail Dialog
        state.selectedEntryForDetail?.let { selected ->
            Dialog(onDismissRequest = { onSelectEntry(null) }) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .fillMaxHeight(0.85f),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                    border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(20.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "Topic Blueprint",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold,
                                color = TextPrimary
                            )
                            IconButton(onClick = { onSelectEntry(null) }) {
                                Icon(Icons.Default.Close, contentDescription = "Close", tint = TextSecondary)
                            }
                        }

                        HorizontalDivider(color = BorderSubtle, modifier = Modifier.padding(vertical = 10.dp))

                        LazyColumn(
                            modifier = Modifier.weight(1f),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            item {
                                Text(
                                    text = selected.title,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = StudioPrimary
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = "ID: ${selected.id} | Pillar: ${selected.contentPillar} | Format: ${if (selected.isShort) "Short (9:16)" else "Long (16:9)"}",
                                    fontSize = 11.sp,
                                    color = TextMuted
                                )
                            }

                            item {
                                Text(text = "Full Narration Script", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                                Spacer(modifier = Modifier.height(4.dp))
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(8.dp))
                                        .background(StudioSurfaceCard)
                                        .padding(12.dp)
                                ) {
                                    Text(text = selected.narration, fontSize = 13.sp, color = TextSecondary, lineHeight = 18.sp)
                                }
                            }

                            item {
                                Text(
                                    text = "Beats & Semantic Footage (${selected.beats.size} beats)",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = TextPrimary
                                )
                                Spacer(modifier = Modifier.height(6.dp))
                                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    selected.beats.forEachIndexed { idx, beat ->
                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clip(RoundedCornerShape(6.dp))
                                                .background(StudioSurfaceCard)
                                                .padding(8.dp),
                                            verticalAlignment = Alignment.Top
                                        ) {
                                            Text(
                                                text = "#${idx + 1}",
                                                fontSize = 11.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = StudioPrimary,
                                                modifier = Modifier.width(28.dp)
                                            )
                                            Column(modifier = Modifier.weight(1f)) {
                                                Text(text = beat.t, fontSize = 12.sp, color = TextPrimary)
                                                if (beat.tags.isNotEmpty()) {
                                                    Spacer(modifier = Modifier.height(2.dp))
                                                    Text(
                                                        text = "Tags: ${beat.tags.joinToString(", ")}",
                                                        fontSize = 10.sp,
                                                        color = StudioSecondary
                                                    )
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            if (selected.verifiedSources.isNotEmpty()) {
                                item {
                                    Text(text = "Verified Sources & Demand Evidence", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text(text = "Sources: ${selected.verifiedSources.joinToString(", ")}", fontSize = 12.sp, color = TextSecondary)
                                    if (selected.demandEvidence.isNotBlank()) {
                                        Text(text = "Evidence: ${selected.demandEvidence}", fontSize = 11.sp, color = StudioAccentGreen)
                                    }
                                }
                            }
                        }

                        HorizontalDivider(color = BorderSubtle, modifier = Modifier.padding(vertical = 10.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            OutlinedButton(
                                onClick = { onSelectEntry(null) },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Text("Close", color = TextSecondary)
                            }
                            if (isEntryEligible(selected)) {
                                Button(
                                    onClick = { onStartProduction(selected) },
                                    modifier = Modifier.weight(1f),
                                    shape = RoundedCornerShape(8.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = StudioPrimary)
                                ) {
                                    Text("Produce Video", color = Color.Black, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
