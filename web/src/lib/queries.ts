import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  api,
  filterQuery,
  toQuery,
  type Event,
  type FilterParams,
  type Histogram,
  type Meta,
  type Summary,
  type Trend,
  type Weighing,
  type Weighings,
} from './api'

// Live views refresh in the background; historical ranges are immutable enough to cache.
const live = (includesToday: boolean) => (includesToday ? 15_000 : false)

export const useMeta = () =>
  useQuery({ queryKey: ['meta'], queryFn: () => api<Meta>('/meta'), staleTime: 60_000, refetchInterval: 60_000 })

export const useSummary = (f: FilterParams, includesToday: boolean) =>
  useQuery({
    queryKey: ['summary', f],
    queryFn: () => api<Summary>(`/summary${filterQuery(f)}`),
    placeholderData: keepPreviousData,
    refetchInterval: live(includesToday),
  })

export const useTrend = (f: FilterParams, interval: string, includesToday: boolean) =>
  useQuery({
    queryKey: ['trend', f, interval],
    queryFn: () => api<Trend>(`/trend${filterQuery(f, { interval })}`),
    placeholderData: keepPreviousData,
    refetchInterval: live(includesToday),
  })

export const useHistogram = (f: FilterParams, includesToday: boolean) =>
  useQuery({
    queryKey: ['histogram', f],
    queryFn: () => api<Histogram>(`/histogram${filterQuery(f, { bins: 36 })}`),
    placeholderData: keepPreviousData,
    refetchInterval: live(includesToday),
  })

export const useWeighings = (f: FilterParams, before: string | undefined, judgement: string[], limit = 50) =>
  useQuery({
    queryKey: ['weighings', f, before, judgement, limit],
    queryFn: () => api<Weighings>(`/weighings${filterQuery(f, { before, judgement, limit })}`),
    placeholderData: keepPreviousData,
  })

export const useRecent = (machineId: number, limit = 240) =>
  useQuery({
    queryKey: ['recent', machineId, limit],
    queryFn: () => api<Weighing[]>(`/machines/${machineId}/recent${toQuery({ limit })}`),
    staleTime: Infinity,
  })

export const useEvents = (machineId?: number, limit = 30) =>
  useQuery({
    queryKey: ['events', machineId, limit],
    queryFn: () => api<Event[]>(`/events${toQuery({ machine_id: machineId, limit })}`),
    refetchInterval: 20_000,
  })
