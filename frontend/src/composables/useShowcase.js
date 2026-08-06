import { computed, reactive } from 'vue'
import {
  architectureLayers,
  boundaryCards,
  challengeCards,
  heroStats,
  highlightGroups,
  homeCapabilityCards,
  homeResultPreview,
  homeSurfaceCards,
  homeValueCards,
  overviewCards,
  resultCards,
  resultLeaderboard,
  resultMetrics,
  workflowSteps,
} from '../content/publicContent'

const showcaseState = reactive({
  activeCandidateName: resultLeaderboard[0]?.name || 'Li2S6',
})

export function useShowcase() {
  const activeCandidate = computed(() => {
    return resultLeaderboard.find(item => item.name === showcaseState.activeCandidateName) || resultLeaderboard[0]
  })

  function selectCandidate(candidateName) {
    showcaseState.activeCandidateName = candidateName
  }

  return {
    showcaseState,
    activeCandidate,
    selectCandidate,
    heroStats,
    overviewCards,
    challengeCards,
    workflowSteps,
    resultCards,
    resultMetrics,
    resultLeaderboard,
    architectureLayers,
    boundaryCards,
    highlightGroups,
    homeCapabilityCards,
    homeValueCards,
    homeResultPreview,
    homeSurfaceCards,
  }
}
