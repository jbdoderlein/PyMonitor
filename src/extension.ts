import * as vscode from 'vscode';
import axios from 'axios';

const SERVER_URL = 'http://127.0.0.1:5000/api'; // Replace with your server URL

class ExecutionCodeLensProvider implements vscode.CodeLensProvider {
    async provideCodeLenses(document: vscode.TextDocument): Promise<vscode.CodeLens[]> {
        const codeLenses: vscode.CodeLens[] = [];
        
        try {
            const response = await axios.get(`${SERVER_URL}/functions`, {
                params: { filePath: document.fileName }
            });

            response.data.forEach((fn: { name: string; line: number; count: number }) => {
                const line = document.lineAt(fn.line - 1);
                const range = new vscode.Range(
                    new vscode.Position(fn.line - 1, 0),
                    new vscode.Position(fn.line - 1, line.text.length)
                );

                const codeLens = new vscode.CodeLens(range, {
                    title: `📊 View Executions (${fn.count})`,
                    command: 'extension.showExecutions',
                    arguments: [fn.name, fn.line]
                });
                
                codeLenses.push(codeLens);
            });
        } catch (error) {
            console.error('Error fetching functions:', error);
        }
        
        return codeLenses;
    }
}

export function activate(context: vscode.ExtensionContext) {
    let currentDecorations: vscode.TextEditorDecorationType[] = [];
    let statusBarItem: vscode.StatusBarItem;

    // Create status bar item for execution selection
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'extension.selectExecution';
    context.subscriptions.push(statusBarItem);

    // Register command for selecting executions
    let disposable = vscode.commands.registerCommand('extension.selectExecution', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        try {
            const response = await axios.get(`${SERVER_URL}/executions`, {
                params: { filePath: editor.document.fileName }
            });
            
            const items = response.data.map((exec: any) => ({
                label: exec.functionName,
                description: `Args: ${exec.args.join(', ')}; Return: ${exec.return}`,
            } as vscode.QuickPickItem & { executionId: string }));

            const selected = await vscode.window.showQuickPick(items);
            if (selected) {
                // Now TypeScript knows selected is a QuickPickItem with executionId
                vscode.window.showInformationMessage(`Selected execution: ${selected}`);
            }
        } catch (error) {
            vscode.window.showErrorMessage('Error fetching executions');
        }
    });

    context.subscriptions.push(disposable);

    // Register CodeLens provider
    const codeLensProvider = new ExecutionCodeLensProvider();
    context.subscriptions.push(
        vscode.languages.registerCodeLensProvider(
            { language: 'python' }, 
            codeLensProvider
        )
    );

    // Register command to show executions
    context.subscriptions.push(
        vscode.commands.registerCommand('extension.showExecutions', async (functionName: string, lineNumber: number) => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            try {
                const response = await axios.get(`${SERVER_URL}/executions`, {
                    params: { 
                        filePath: editor.document.fileName,
                        functionName: functionName,
                        line: lineNumber
                    }
                });

                const items = response.data.map((exec: any) => ({
                    label: `Args: ${Object.entries(exec.args).map(([k, v]) => `${k}=${v}`).join(', ')}`,
                    description: `Return: ${exec.return}`,
                    detail: `Called at ${new Date(exec.timestamp).toLocaleString()}, ${exec.exec_time}s`,
                    executionId: exec.id
                }));

                const selected = await vscode.window.showQuickPick(items, {
                    placeHolder: `Select execution of ${functionName} to inspect`
                });

                
                if (selected) {
                    // Handle selected execution (could show details in webview)
                    vscode.window.showInformationMessage(`Selected execution: ${selected}`);
                }
            } catch (error) {
                vscode.window.showErrorMessage('Error fetching executions');
            }
        })
    );

    // Refresh CodeLens when document changes
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(document => {
            if (document.languageId === 'python') {
                codeLensProvider.provideCodeLenses(document);
            }
        })
    );
}

export function deactivate() {} 