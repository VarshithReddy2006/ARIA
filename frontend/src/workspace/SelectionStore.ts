import type { PinnedItem } from './types';

export class SelectionStore {
  private selectedFile: string | null = "backend/api.py";
  private selectedNodeId: string | null = "backend/api.py";
  private selectedConcept: string | null = "Routing";
  private selectedLayer: string | null = "Presentation";
  private selectedScenario: string | null = null;
  private multiSelection: string[] = ["backend/api.py"];
  private pinnedItems: PinnedItem[] = [
    { id: "backend/api.py", label: "api.py", type: "file" },
  ];

  public getSelectedFile(): string | null {
    return this.selectedFile;
  }

  public getSelectedNodeId(): string | null {
    return this.selectedNodeId;
  }

  public getSelectedConcept(): string | null {
    return this.selectedConcept;
  }

  public getSelectedLayer(): string | null {
    return this.selectedLayer;
  }

  public getMultiSelection(): string[] {
    return [...this.multiSelection];
  }

  public getPinnedItems(): PinnedItem[] {
    return [...this.pinnedItems];
  }

  public setSelectedFile(file: string | null): void {
    this.selectedFile = file;
    if (file) {
      this.selectedNodeId = file;
      if (!this.multiSelection.includes(file)) {
        this.multiSelection = [file, ...this.multiSelection.slice(0, 4)];
      }
    }
  }

  public setSelectedConcept(concept: string | null): void {
    this.selectedConcept = concept;
  }

  public setSelectedLayer(layer: string | null): void {
    this.selectedLayer = layer;
  }

  public pinItem(item: PinnedItem): void {
    if (!this.pinnedItems.some((p) => p.id === item.id)) {
      this.pinnedItems.push(item);
    }
  }

  public unpinItem(id: string): void {
    this.pinnedItems = this.pinnedItems.filter((p) => p.id !== id);
  }
}
