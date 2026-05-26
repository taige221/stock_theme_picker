import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, RotateCcw, Save, Search, Settings2 } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, AppPage, Badge, Button, Card, InlineAlert, Input, PaperHero, PaperHeroHeader, Select } from '../components/common';
import type { RuntimeSettingField, RuntimeSettingSection, RuntimeSettingsResponse } from '../api/settings';
import { settingsApi } from '../api/settings';

const booleanOptions = [
  { value: 'true', label: '启用' },
  { value: 'false', label: '关闭' },
];

const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<RuntimeSettingsResponse | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const response = await settingsApi.getRuntimeSettings();
      setSettings(response);
      setFormValues(
        response.sections.reduce<Record<string, string>>((acc, section) => {
          section.fields.forEach((field) => {
            acc[field.key] = field.value ?? '';
          });
          return acc;
        }, {})
      );
    } catch (loadError) {
      setError(getParsedApiError(loadError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSettings();
  }, []);

  const flatFields = useMemo(
    () => settings?.sections.flatMap((section) => section.fields) ?? [],
    [settings]
  );

  const dirtyKeys = useMemo(
    () =>
      flatFields
        .filter((field) => (formValues[field.key] ?? '') !== (field.value ?? ''))
        .map((field) => field.key),
    [flatFields, formValues]
  );

  const restartRequiredDirtyFields = useMemo(
    () => flatFields.filter((field) => field.requiresRestart && dirtyKeys.includes(field.key)),
    [dirtyKeys, flatFields]
  );

  const filteredSections = useMemo(() => {
    if (!settings) {
      return [];
    }

    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return settings.sections;
    }

    return settings.sections
      .map((section) => {
        const sectionMatches = [section.title, section.description ?? '', section.id]
          .join(' ')
          .toLowerCase()
          .includes(query);

        if (sectionMatches) {
          return section;
        }

        return {
          ...section,
          fields: section.fields.filter((field) =>
            [field.key, field.label, field.description ?? ''].join(' ').toLowerCase().includes(query)
          ),
        };
      })
      .filter((section) => section.fields.length > 0);
  }, [searchQuery, settings]);

  const visibleFieldCount = useMemo(
    () => filteredSections.reduce((count, section) => count + section.fields.length, 0),
    [filteredSections]
  );

  const handleSave = async () => {
    if (!dirtyKeys.length) {
      setMessage('当前没有需要保存的改动。');
      return;
    }

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const payload = dirtyKeys.reduce<Record<string, string>>((acc, key) => {
        acc[key] = formValues[key] ?? '';
        return acc;
      }, {});
      const response = await settingsApi.updateRuntimeSettings(payload);
      setMessage(response.message);
      await loadSettings();
    } catch (saveError) {
      setError(getParsedApiError(saveError));
    } finally {
      setSaving(false);
    }
  };

  const renderField = (field: RuntimeSettingField) => {
    const value = formValues[field.key] ?? '';
    const commonHint = [
      field.description,
      field.requiresRestart ? '保存后需重启服务才能完全生效。' : null,
    ]
      .filter(Boolean)
      .join(' ');

    if (field.inputType === 'select') {
      return (
        <Select
          value={value}
          onChange={(nextValue) => setFormValues((prev) => ({ ...prev, [field.key]: nextValue }))}
          options={field.options}
          label={field.label}
          className="w-full"
        />
      );
    }

    if (field.inputType === 'boolean') {
      return (
        <Select
          value={value || 'false'}
          onChange={(nextValue) => setFormValues((prev) => ({ ...prev, [field.key]: nextValue }))}
          options={booleanOptions}
          label={field.label}
          className="w-full"
        />
      );
    }

    return (
      <Input
        label={field.label}
        type={field.inputType === 'password' ? 'password' : field.inputType === 'number' ? 'number' : 'text'}
        value={value}
        placeholder={field.placeholder ?? ''}
        hint={commonHint || undefined}
        allowTogglePassword={field.inputType === 'password'}
        onChange={(event) => setFormValues((prev) => ({ ...prev, [field.key]: event.target.value }))}
      />
    );
  };

  const renderSection = (section: RuntimeSettingSection) => (
    <Card key={section.id} variant="bordered" padding="lg" className="paper-panel rounded-[24px]">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-semibold text-foreground">{section.title}</h2>
            <Badge variant="info" className="border-0 px-3 py-1">
              {section.fields.length} 项
            </Badge>
            {section.fields.some((field) => (formValues[field.key] ?? '') !== (field.value ?? '')) ? (
              <Badge variant="warning" className="border-0 px-3 py-1">
                有未保存改动
              </Badge>
            ) : null}
          </div>
          {section.description ? (
            <p className="mt-2 text-sm leading-6 text-secondary-text">{section.description}</p>
          ) : null}
        </div>
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        {section.fields.map((field) => {
          const commonHint = [
            field.description,
            field.requiresRestart ? '保存后需重启服务才能完全生效。' : null,
          ]
            .filter(Boolean)
            .join(' ');
          const isDirty = (formValues[field.key] ?? '') !== (field.value ?? '');

          return (
            <div
              key={field.key}
              className={`paper-list-card px-4 py-4 ${
                isDirty ? 'border-foreground/16 bg-card/96' : ''
              }`}
            >
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  {isDirty ? (
                    <Badge variant="info" className="border-0 px-3 py-1">
                      已修改
                    </Badge>
                  ) : null}
                  {field.requiresRestart ? (
                    <Badge variant="warning" className="border-0 px-3 py-1">
                      需重启
                    </Badge>
                  ) : null}
                  {field.secret ? (
                    <Badge variant="default" className="border-0 px-3 py-1">
                      敏感字段
                    </Badge>
                  ) : null}
                </div>
                {isDirty ? (
                  <button
                    type="button"
                    className="paper-chip px-3 py-1 text-xs"
                    onClick={() => setFormValues((prev) => ({ ...prev, [field.key]: field.value ?? '' }))}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    重置
                  </button>
                ) : null}
              </div>
              {renderField(field)}
              {field.inputType === 'select' || field.inputType === 'boolean' ? (
                <p className="mt-2 text-xs leading-6 text-secondary-text">{commonHint || ' '}</p>
              ) : null}
              <p className="mt-3 text-[11px] uppercase tracking-[0.14em] text-muted-text/80">{field.key}</p>
            </div>
          );
        })}
      </div>
    </Card>
  );

  return (
    <AppPage className="settings-page space-y-6 !max-w-[1680px] px-3 md:px-5 lg:px-6">
      <PaperHero>
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <PaperHeroHeader
            eyebrow="Runtime Settings"
            title="在界面里直接维护常用环境变量"
            description="这里只开放适合 Web UI 调整的白名单字段。保存后会写回当前 `.env`，并重载当前进程配置；带“需重启”的字段仍建议重启服务确认完全生效。"
            icon={<Settings2 className="h-7 w-7" />}
          />

          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-[280px] flex-1">
              <Input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="搜索设置项，例如 tushare、timeout、数据库、模型"
                trailingAction={<Search className="h-4 w-4 text-secondary-text" />}
              />
            </div>
            <Button variant="secondary" className="rounded-2xl" onClick={() => void loadSettings()} disabled={loading || saving}>
              <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              重新读取
            </Button>
            <Button className="rounded-2xl" onClick={() => void handleSave()} disabled={loading || saving}>
              <Save className="mr-2 h-4 w-4" />
              {saving ? '保存中...' : dirtyKeys.length ? `保存 ${dirtyKeys.length} 项改动` : '保存设置'}
            </Button>
          </div>
        </div>

        {settings?.envFile ? (
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Badge variant="info" className="border-0 px-3 py-1">当前 .env</Badge>
            <code className="paper-code-pill">
              {settings.envFile}
            </code>
            <Badge variant="default" className="border-0 px-3 py-1">
              当前展示 {visibleFieldCount} 项
            </Badge>
            <Badge variant={dirtyKeys.length ? 'warning' : 'success'} className="border-0 px-3 py-1">
              {dirtyKeys.length ? `${dirtyKeys.length} 项待保存` : '全部已同步'}
            </Badge>
          </div>
        ) : null}
      </PaperHero>

      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}
      {message ? <InlineAlert variant="success" title="设置已处理" message={message} /> : null}
      {restartRequiredDirtyFields.length ? (
        <InlineAlert
          variant="warning"
          title="这些改动建议重启服务"
          message={`当前改动里有 ${restartRequiredDirtyFields.length} 项属于启动期参数：${restartRequiredDirtyFields.map((field) => field.label).join('、')}`}
        />
      ) : null}
      {settings?.validationIssues.length ? (
        <InlineAlert
          variant="info"
          title="当前配置里还有待确认项"
          message={settings.validationIssues.slice(0, 4).join('；')}
        />
      ) : null}
      {loading ? (
        <InlineAlert variant="info" title="正在加载设置" message="正在读取服务端白名单配置与当前值。" />
      ) : null}
      {!loading && settings && filteredSections.length === 0 ? (
        <InlineAlert
          variant="warning"
          title="没有匹配到设置项"
          message={`当前搜索词“${searchQuery.trim()}”没有匹配到可编辑字段，可以换个关键词再试。`}
        />
      ) : null}

      {!loading && settings ? filteredSections.map(renderSection) : null}
    </AppPage>
  );
};

export default SettingsPage;
