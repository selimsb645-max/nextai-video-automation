package com.example.nextaistudio

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.nextaistudio.ui.screens.*
import com.example.nextaistudio.ui.theme.*
import com.example.nextaistudio.ui.viewmodel.AppScreen
import com.example.nextaistudio.ui.viewmodel.NextAIViewModel

class MainActivity : ComponentActivity() {

    private val viewModel: NextAIViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            NextAIStudioTheme {
                val state by viewModel.uiState.collectAsStateWithLifecycle()
                val snackbarHostState = remember { SnackbarHostState() }

                // Show notification snackbar when available
                LaunchedEffect(state.notificationMessage) {
                    state.notificationMessage?.let { msg ->
                        snackbarHostState.showSnackbar(msg)
                        viewModel.clearNotification()
                    }
                }

                // Handle back press
                BackHandler(enabled = state.currentScreen != AppScreen.DASHBOARD) {
                    viewModel.navigateTo(AppScreen.DASHBOARD)
                }

                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = StudioDarkBackground,
                    contentWindowInsets = WindowInsets.safeDrawing,
                    snackbarHost = { SnackbarHost(snackbarHostState) },
                    topBar = {
                        StudioTopBar(
                            currentScreen = state.currentScreen,
                            onNavigate = { viewModel.navigateTo(it) }
                        )
                    },
                    bottomBar = {
                        StudioBottomNavigation(
                            currentScreen = state.currentScreen,
                            onSelectScreen = { viewModel.navigateTo(it) }
                        )
                    }
                ) { innerPadding ->
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(innerPadding)
                    ) {
                        when (state.currentScreen) {
                            AppScreen.DASHBOARD -> DashboardScreen(
                                state = state,
                                onNavigate = { viewModel.navigateTo(it) },
                                onStartPipelineWithFirstEligible = {
                                    val first = state.libraryEntries.firstOrNull { viewModel.isEntryEligible(it) }
                                    if (first != null) {
                                        viewModel.startProductionForEntry(first)
                                    }
                                }
                            )
                            AppScreen.LIBRARY -> LibraryScreen(
                                state = state,
                                onFilterFormat = { viewModel.setLibraryFilterFormat(it) },
                                onFilterPillar = { viewModel.setLibraryFilterPillar(it) },
                                onSearchQuery = { viewModel.setLibrarySearchQuery(it) },
                                onSelectEntry = { viewModel.selectEntryForDetail(it) },
                                onStartProduction = { viewModel.startProductionForEntry(it) },
                                isEntryEligible = { viewModel.isEntryEligible(it) }
                            )
                            AppScreen.PIPELINE -> PipelineStudioScreen(
                                viewModel = viewModel,
                                state = state
                            )
                            AppScreen.RUNS -> RunsScreen(
                                state = state,
                                onSelectRun = { viewModel.selectRunForDetail(it) }
                            )
                            AppScreen.WORKFLOWS -> WorkflowsScreen(
                                state = state,
                                onToggleWorkflow = { viewModel.toggleWorkflow(it) }
                            )
                            AppScreen.PREFLIGHT -> PreflightScreen(
                                state = state,
                                onRunDiagnostics = { viewModel.triggerPreflightDiagnostics() }
                            )
                            AppScreen.POLICY -> PolicyScreen()
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StudioTopBar(
    currentScreen: AppScreen,
    onNavigate: (AppScreen) -> Unit
) {
    TopAppBar(
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(28.dp)
                        .clip(androidx.compose.foundation.shape.RoundedCornerShape(6.dp))
                        .background(StudioAccentRed),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.PlayArrow,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(18.dp)
                    )
                }
                Spacer(modifier = Modifier.width(10.dp))
                Column {
                    Text(
                        text = "NextAI Studio",
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary
                    )
                    Text(
                        text = when (currentScreen) {
                            AppScreen.DASHBOARD -> "Command Center"
                            AppScreen.LIBRARY -> "Content Library"
                            AppScreen.PIPELINE -> "Production Studio"
                            AppScreen.RUNS -> "Runs & Uploads"
                            AppScreen.WORKFLOWS -> "Automation Templates"
                            AppScreen.PREFLIGHT -> "Preflight Diagnostics"
                            AppScreen.POLICY -> "Editorial Policy"
                        },
                        fontSize = 11.sp,
                        color = StudioPrimary
                    )
                }
            }
        },
        actions = {
            IconButton(
                onClick = { onNavigate(AppScreen.WORKFLOWS) },
                modifier = Modifier.testTag("topbar_workflows_btn")
            ) {
                Icon(
                    imageVector = Icons.Default.AccountTree,
                    contentDescription = "Workflows",
                    tint = if (currentScreen == AppScreen.WORKFLOWS) StudioPrimary else TextSecondary
                )
            }
            IconButton(
                onClick = { onNavigate(AppScreen.PREFLIGHT) },
                modifier = Modifier.testTag("topbar_preflight_btn")
            ) {
                Icon(
                    imageVector = Icons.Default.Speed,
                    contentDescription = "Preflight",
                    tint = if (currentScreen == AppScreen.PREFLIGHT) StudioPrimary else TextSecondary
                )
            }
            IconButton(
                onClick = { onNavigate(AppScreen.POLICY) },
                modifier = Modifier.testTag("topbar_policy_btn")
            ) {
                Icon(
                    imageVector = Icons.Default.Policy,
                    contentDescription = "Policy",
                    tint = if (currentScreen == AppScreen.POLICY) StudioPrimary else TextSecondary
                )
            }
        },
        colors = TopAppBarDefaults.topAppBarColors(containerColor = StudioSurfaceDark)
    )
}

@Composable
private fun StudioBottomNavigation(
    currentScreen: AppScreen,
    onSelectScreen: (AppScreen) -> Unit
) {
    NavigationBar(
        containerColor = StudioSurfaceDark,
        contentColor = TextPrimary,
        tonalElevation = 4.dp
    ) {
        NavigationBarItem(
            selected = currentScreen == AppScreen.DASHBOARD,
            onClick = { onSelectScreen(AppScreen.DASHBOARD) },
            icon = { Icon(Icons.Default.Dashboard, contentDescription = "Dashboard") },
            label = { Text("Dashboard", fontSize = 11.sp) },
            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = Color.Black,
                selectedTextColor = StudioPrimary,
                indicatorColor = StudioPrimary,
                unselectedIconColor = TextSecondary,
                unselectedTextColor = TextMuted
            ),
            modifier = Modifier.testTag("nav_item_dashboard")
        )

        NavigationBarItem(
            selected = currentScreen == AppScreen.LIBRARY,
            onClick = { onSelectScreen(AppScreen.LIBRARY) },
            icon = { Icon(Icons.Default.VideoLibrary, contentDescription = "Library") },
            label = { Text("Library", fontSize = 11.sp) },
            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = Color.Black,
                selectedTextColor = StudioPrimary,
                indicatorColor = StudioPrimary,
                unselectedIconColor = TextSecondary,
                unselectedTextColor = TextMuted
            ),
            modifier = Modifier.testTag("nav_item_library")
        )

        NavigationBarItem(
            selected = currentScreen == AppScreen.PIPELINE,
            onClick = { onSelectScreen(AppScreen.PIPELINE) },
            icon = { Icon(Icons.Default.MovieFilter, contentDescription = "Pipeline") },
            label = { Text("Studio", fontSize = 11.sp) },
            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = Color.Black,
                selectedTextColor = StudioPrimary,
                indicatorColor = StudioPrimary,
                unselectedIconColor = TextSecondary,
                unselectedTextColor = TextMuted
            ),
            modifier = Modifier.testTag("nav_item_pipeline")
        )

        NavigationBarItem(
            selected = currentScreen == AppScreen.RUNS,
            onClick = { onSelectScreen(AppScreen.RUNS) },
            icon = { Icon(Icons.Default.History, contentDescription = "Runs") },
            label = { Text("Runs", fontSize = 11.sp) },
            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = Color.Black,
                selectedTextColor = StudioPrimary,
                indicatorColor = StudioPrimary,
                unselectedIconColor = TextSecondary,
                unselectedTextColor = TextMuted
            ),
            modifier = Modifier.testTag("nav_item_runs")
        )
    }
}
